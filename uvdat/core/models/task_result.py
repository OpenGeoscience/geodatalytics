from __future__ import annotations

import contextlib
from contextvars import ContextVar
import json
import logging

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

logger = logging.getLogger(__name__)

# Set while running in a context (e.g. `manage.py ingest`) where TaskResult
# WebSocket notifications are meaningless: tasks run synchronously with no
# client session listening. When set, result_post_save skips the push entirely
# rather than attempting it and logging a warning.
_suppress_notifications: ContextVar[bool] = ContextVar(
    "suppress_task_notifications", default=False
)


@contextlib.contextmanager
def suppress_task_notifications():
    """Silence TaskResult WebSocket notifications for the current context."""
    token = _suppress_notifications.set(True)
    try:
        yield
    finally:
        _suppress_notifications.reset(token)


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
    # In contexts such as `manage.py ingest`, tasks run synchronously with no
    # client session listening, so the push is meaningless -- skip it silently
    # (no attempt, no warning). See suppress_task_notifications().
    if _suppress_notifications.get():
        return

    # Prevent circular import
    from uvdat.core.rest.serializers import TaskResultSerializer  # noqa: PLC0415

    payload = TaskResultSerializer(instance).data
    group_name = "conversion"
    if instance.project:
        group_name = f"analytics_{instance.project.id}"
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    # This WebSocket push streams live TaskResult updates to browser clients
    # subscribed to a channel group. It is best-effort: a failed notification
    # must never abort the surrounding TaskResult.save(). Failures are logged at
    # WARNING so a genuinely broken channel layer in production is still visible.
    try:
        async_to_sync(channel_layer.group_send)(
            group_name, {"type": "send_notification", "message": json.dumps(payload)}
        )
    except Exception:  # noqa: BLE001 - notification failures must never propagate
        logger.warning(
            "Failed to send TaskResult notification for %s to group %r",
            instance,
            group_name,
            exc_info=True,
        )
