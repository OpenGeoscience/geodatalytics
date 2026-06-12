from __future__ import annotations

from django.db import models
from s3_file_field import S3FileField

from .layer import LayerFrame
from .styles import LayerStyle


class RasterFramePreview(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    layer_style = models.ForeignKey(
        LayerStyle,
        related_name="frame_previews",
        on_delete=models.CASCADE,
    )
    layer_frame = models.ForeignKey(
        LayerFrame,
        related_name="style_previews",
        on_delete=models.CASCADE,
    )
    image = S3FileField()
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    bounds = models.JSONField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["layer_style", "layer_frame"],
                name="unique_layer_style_layer_frame_preview",
            )
        ]

    def __str__(self):
        return f"Preview style={self.layer_style_id} frame={self.layer_frame_id} ({self.id})"
