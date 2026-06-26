from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

from .data import RasterData, VectorData
from .dataset import Dataset
from .querysets import ProjectQuerySet

if TYPE_CHECKING:
    from uvdat.core.frame_previews.types import FramePreviewData


def default_source_filters():
    return {}


class Layer(models.Model):
    name = models.CharField(max_length=255, default="Layer")
    dataset = models.ForeignKey(Dataset, related_name="layers", on_delete=models.CASCADE)
    metadata = models.JSONField(blank=True, null=True)
    default_style = models.ForeignKey(
        "LayerStyle", null=True, related_name="default_layer", on_delete=models.SET_NULL
    )

    project_filter_path = "dataset__project"
    objects = ProjectQuerySet.as_manager()

    def __str__(self):
        return f"{self.name} ({self.id})"

    def multiframe_raster_frames(self):
        prefetched = getattr(self, "raster_frames", None)
        if prefetched is not None:
            return prefetched
        return list(
            self.frames.filter(raster__isnull=False).select_related("raster").order_by("index")
        )

    def is_multiframe_raster(self) -> bool:
        prefetched = getattr(self, "raster_frames", None)
        if prefetched is not None:
            return len(prefetched) > 1
        return self.frames.filter(raster__isnull=False).count() > 1

    def default_multiframe_previews(self) -> list[FramePreviewData] | None:
        if self.default_style_id is None:
            return None
        return self.default_style.multiframe_previews(layer=self)


class LayerFrame(models.Model):
    name = models.CharField(max_length=255, default="Layer Frame")
    layer = models.ForeignKey(Layer, related_name="frames", on_delete=models.CASCADE)
    vector = models.ForeignKey(VectorData, null=True, on_delete=models.CASCADE)
    raster = models.ForeignKey(RasterData, null=True, on_delete=models.CASCADE)
    index = models.PositiveIntegerField(default=0)
    source_filters = models.JSONField(default=default_source_filters)
    metadata = models.JSONField(blank=True, null=True)

    project_filter_path = "layer__dataset__project"
    objects = ProjectQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(raster__isnull=False) & models.Q(vector__isnull=True))
                | (models.Q(raster__isnull=True) & models.Q(vector__isnull=False)),
                name="exactly_one_data",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.id})"

    def get_data(self):
        if self.raster is not None:
            return self.raster
        return self.vector
