from __future__ import annotations

from django.db import models
from django.dispatch import receiver
from s3_file_field import S3FileField

from .layer import LayerFrame


class PreviewStatus(models.TextChoices):
    CREATING = "creating", "Creating"
    REGENERATING = "regenerating", "Regenerating"
    COMPLETE = "complete", "Complete"
    FAILED = "failed", "Failed"


class RasterFramePreview(models.Model):
    """Cache of one rendered PNG for (frame × raster_style_params fingerprint)."""

    layer_frame = models.ForeignKey(
        LayerFrame,
        related_name="previews",
        on_delete=models.CASCADE,
    )
    # sha256 of the raster_style_params JSON used to render this image
    style_fingerprint = models.CharField(max_length=64)
    # Params used for this render (debug / re-render without a LayerStyle).
    raster_style_params = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16,
        choices=PreviewStatus.choices,
        default=PreviewStatus.CREATING,
    )
    image = S3FileField(blank=True, null=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    bounds = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["layer_frame", "style_fingerprint"],
                name="unique_layer_frame_style_fingerprint_preview",
            )
        ]

    def __str__(self):
        return (
            f"Preview frame={self.layer_frame_id} "
            f"fingerprint={self.style_fingerprint[:8]}… ({self.id})"
        )


@receiver(models.signals.post_delete, sender=RasterFramePreview)
def delete_preview_image(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)
