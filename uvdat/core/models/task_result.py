from __future__ import annotations

import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.utils import timezone

from .project import Project
from .querysets import ProjectQuerySet


class TaskResult(models.Model):
    name = models.CharField(max_length=255)
    task_type = models.CharField(max_length=25)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="task_results", null=True
    )
    inputs = models.JSONField(blank=True, null=True)
    outputs = models.JSONField(blank=True, null=True)
    status = models.TextField(blank=True, default="")
    error = models.TextField(blank=True, default="")
    created = models.DateTimeField(auto_now_add=True, editable=False)
    completed = models.DateTimeField(null=True)
    creator = models.ForeignKey(
        User, related_name="task_results", null=True, on_delete=models.CASCADE
    )
    subscribers = models.ManyToManyField(User, related_name="task_subscriptions", blank=True)

    project_filter_path = "project"
    project_filter_allow_null = True
    objects = ProjectQuerySet.as_manager()

    def __str__(self):
        return f"{self.name} ({self.id})"

    def write_error(self, err):
        if self.error:
            self.error += ", "
        self.error += err
        self.save()

    def write_status(self, stat):
        self.status = stat
        self.save()

    def write_outputs(self, outputs):
        self.outputs = outputs
        self.save()

    def complete(self):
        self.completed = timezone.now()
        seconds = (self.completed - self.created).total_seconds()
        self.status = f"Completed in {seconds:.2f} seconds."
        self.save()

        for subscriber in self.subscribers.all():
            subject = "GeoDatalytics Task Completed"
            message = render_to_string(
                "uvdat/email_task_complete.txt",
                {"task_name": self.name, "link": settings.UVDAT_WEB_URL},
            )
            send_mail(
                subject=subject,
                message=message,
                from_email=None,
                recipient_list=[subscriber],
            )


@receiver(post_save, sender=TaskResult)
def result_post_save(sender, instance, **kwargs):
    # Prevent circular import
    from uvdat.core.rest.serializers import TaskResultSerializer  # noqa: PLC0415

    payload = TaskResultSerializer(instance).data
    group_name = "conversion"
    if instance.project:
        group_name = f"analytics_{instance.project.id}"
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        group_name, {"type": "send_notification", "message": json.dumps(payload)}
    )
