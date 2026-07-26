from __future__ import annotations

import typing

from django.db import models, transaction
from guardian.models import UserObjectPermission
from guardian.shortcuts import assign_perm, get_users_with_perms

from .querysets import ProjectQuerySet

if typing.TYPE_CHECKING:
    from django.contrib.auth.models import User


class DatasetTag(models.Model):
    tag = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ["tag"]

    def __str__(self):
        return self.tag


class Dataset(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, default="")
    category = models.CharField(max_length=25)
    processing = models.BooleanField(default=False)
    tags = models.ManyToManyField(DatasetTag, blank=True)
    metadata = models.JSONField(blank=True, null=True)

    # Dataset permissions are not determined by Project permissions
    project_filter_path = None
    objects = ProjectQuerySet.as_manager()

    class Meta:
        permissions = [("owner", "Can read, write, and delete")]

    def __str__(self):
        return f"{self.name} ({self.id})"

    def owner(self) -> User | None:
        users = typing.cast(
            "list[User]", list(get_users_with_perms(self, only_with_perms_in=["owner"]))
        )
        if len(users) != 1:
            return None
        return users[0]

    @transaction.atomic()
    def set_owner(self, user: User):
        filters = {
            "content_type__app_label": self._meta.app_label,
            "content_type__model": self._meta.model_name,
            "object_pk": self.pk,
        }

        # Remove existing owner
        UserObjectPermission.objects.filter(
            **filters,
            permission__codename="owner",
        ).delete()

        if user is not None:
            # Delete any existing user perms and set owner
            UserObjectPermission.objects.filter(
                **filters,
                user_id__in=[user.id],
            ).delete()
            assign_perm("owner", user, self)

    @transaction.atomic()
    def set_tags(self, tags: list[str]):
        for tag in tags:
            DatasetTag.objects.get_or_create(tag=tag)
        self.tags.set(DatasetTag.objects.filter(tag__in=tags))

    def spawn_conversion_task(
        self,
        *,
        layer_options=None,
        network_options=None,
        region_options=None,
        asynchronous=True,
    ):
        # Prevent circular import
        from uvdat.core.models.task_result import (  # noqa: PLC0415
            TaskResult,
            suppress_task_notifications,
        )
        from uvdat.core.tasks.dataset import convert_dataset  # noqa: PLC0415

        convert_dataset_signature = convert_dataset.s(
            dataset_id=self.id,
            layer_options=layer_options,
            network_options=network_options,
            region_options=region_options,
        )

        if asynchronous:
            result = TaskResult.objects.create(
                name=f"Conversion of Dataset {self.name}",
                task_type="conversion",
                inputs={
                    "dataset_id": self.id,
                    "layer_options": layer_options,
                    "network_options": network_options,
                    "region_options": region_options,
                },
                status="Initializing task...",
                creator=self.owner(),
            )
            convert_dataset_signature.delay(result_id=result.id)
            return result
        else:
            with suppress_task_notifications():
                convert_dataset_signature.apply()
            return None
