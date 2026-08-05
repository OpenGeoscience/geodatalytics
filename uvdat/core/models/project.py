from __future__ import annotations

import typing

from django.contrib.gis.db import models as geo_models
from django.db import models, transaction
from guardian.models import UserObjectPermission
from guardian.shortcuts import assign_perm, get_users_with_perms, remove_perm

from .dataset import Dataset
from .querysets import ProjectQuerySet

if typing.TYPE_CHECKING:
    from django.contrib.auth.models import User


class Project(models.Model):
    name = models.CharField(max_length=255, unique=True)
    default_map_center = geo_models.PointField()
    default_map_zoom = models.FloatField(default=10)
    datasets = models.ManyToManyField(Dataset, blank=True)

    project_filter_path = "pk"
    objects = ProjectQuerySet.as_manager()

    class Meta:
        permissions = [
            ("owner", "Can read, write, and delete"),
            ("collaborator", "Can read and write"),
            ("follower", "Can read"),
        ]

    def __str__(self):
        return f"{self.name} ({self.id})"

    def owner(self) -> User:
        users = typing.cast(
            "list[User]", list(get_users_with_perms(self, only_with_perms_in=["owner"]))
        )
        if len(users) != 1:
            raise RuntimeError("Project must have exactly one owner")

        return users[0]

    def collaborators(self) -> list[User]:
        return typing.cast(
            "list[User]", list(get_users_with_perms(self, only_with_perms_in=["collaborator"]))
        )

    def followers(self):
        return typing.cast(
            "list[User]", list(get_users_with_perms(self, only_with_perms_in=["follower"]))
        )

    def user_can_edit(self, user):
        return user.is_superuser or self.owner() == user or user in self.collaborators()

    @transaction.atomic()
    def delete_users_perms(self, users: list[User]):
        """Delete all permissions a user may have on this project."""
        user_ids = [user.id for user in users]
        UserObjectPermission.objects.filter(
            content_type__app_label=self._meta.app_label,
            content_type__model=self._meta.model_name,
            object_pk=self.pk,
            user_id__in=user_ids,
        ).delete()

    @transaction.atomic()
    def set_owner(self, user: User):
        # Remove existing owner
        UserObjectPermission.objects.filter(
            content_type__app_label=self._meta.app_label,
            content_type__model=self._meta.model_name,
            object_pk=self.pk,
            permission__codename="owner",
        ).delete()

        # Delete any existing user perms and set owner
        self.delete_users_perms([user])
        assign_perm("owner", user, self)

    @transaction.atomic()
    def set_collaborators(self, users: list[User]):
        for user in get_users_with_perms(self, only_with_perms_in=["collaborator"]):
            remove_perm("collaborator", user, self)
        self.delete_users_perms(users)
        for user in users:
            assign_perm("collaborator", user, self)

    @transaction.atomic()
    def set_followers(self, users: list[User]):
        for user in get_users_with_perms(self, only_with_perms_in=["follower"]):
            remove_perm("follower", user, self)
        self.delete_users_perms(users)
        for user in users:
            assign_perm("follower", user, self)

    @transaction.atomic()
    def set_permissions(
        self,
        owner: User,
        collaborator: list[User] | None = None,
        follower: list[User] | None = None,
    ):
        self.set_owner(owner)
        self.set_collaborators(collaborator or [])
        self.set_followers(follower or [])
