from __future__ import annotations

from django.db.models import Prefetch, QuerySet

from uvdat.core.models import Layer, LayerFrame, LayerStyle, RasterFramePreview

RASTER_FRAMES_QUERYSET = (
    LayerFrame.objects.filter(raster__isnull=False).select_related("raster").order_by("index")
)

FRAME_PREVIEWS_ON_FRAME_PREFETCH = Prefetch(
    "previews",
    queryset=RasterFramePreview.objects.all(),
)

LAYER_RASTER_FRAMES_PREFETCH = Prefetch(
    "frames",
    queryset=RASTER_FRAMES_QUERYSET.prefetch_related(FRAME_PREVIEWS_ON_FRAME_PREFETCH),
    to_attr="_raster_frames",
)

STYLE_LAYER_RASTER_FRAMES_PREFETCH = Prefetch(
    "layer__frames",
    queryset=RASTER_FRAMES_QUERYSET.prefetch_related(FRAME_PREVIEWS_ON_FRAME_PREFETCH),
    to_attr="_raster_frames",
)


def layer_queryset_with_previews(
    queryset: QuerySet | None = None,
    *,
    for_layer_style: bool = False,
) -> QuerySet:
    # Preview status is computed in Python from prefetched frame previews
    # (keyed by fingerprint), not via SQL annotations on a LayerStyle FK.
    if for_layer_style:
        qs = queryset if queryset is not None else LayerStyle.objects.all()
        return qs.select_related("layer", "layer__default_style").prefetch_related(
            STYLE_LAYER_RASTER_FRAMES_PREFETCH,
        )

    qs = queryset if queryset is not None else Layer.objects.all()
    return qs.select_related("dataset", "default_style").prefetch_related(
        LAYER_RASTER_FRAMES_PREFETCH,
    )
