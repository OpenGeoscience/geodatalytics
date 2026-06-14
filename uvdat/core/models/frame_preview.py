from __future__ import annotations

from django.db import models
from django.dispatch import receiver
from s3_file_field import S3FileField

from .layer import LayerFrame
from .styles import LayerStyle


class RasterFramePreview(models.Model):
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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["layer_style", "layer_frame"],
                name="unique_layer_style_layer_frame_preview",
            )
        ]

    def __str__(self):
        return f"Preview style={self.layer_style_id} frame={self.layer_frame_id} ({self.id})"


@receiver(models.signals.post_delete, sender=RasterFramePreview)
def delete_preview_image(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)
