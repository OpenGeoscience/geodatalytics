from __future__ import annotations

from django.db.models import Prefetch, QuerySet

from uvdat.core.models import Layer, LayerFrame, LayerStyle, RasterFramePreview

RASTER_FRAMES_QUERYSET = (
    LayerFrame.objects.filter(raster__isnull=False).select_related("raster").order_by("index")
)

FRAME_PREVIEWS_PREFETCH = Prefetch(
    "frame_previews",
    queryset=RasterFramePreview.objects.select_related("layer_frame"),
)

LAYER_RASTER_FRAMES_PREFETCH = Prefetch(
    "frames",
    queryset=RASTER_FRAMES_QUERYSET,
    to_attr="raster_frames",
)

STYLE_LAYER_RASTER_FRAMES_PREFETCH = Prefetch(
    "layer__frames",
    queryset=RASTER_FRAMES_QUERYSET,
    to_attr="raster_frames",
)


def layer_queryset_with_previews(
    queryset: QuerySet | None = None,
    *,
    for_layer_style: bool = False,
) -> QuerySet:
    # This is for /layer-styles/?layer={layer_id} so we need to prefetch the frames for all styles
    if for_layer_style:
        qs = queryset if queryset is not None else LayerStyle.objects.all()
        return qs.select_related("layer", "layer__default_style").prefetch_related(
            FRAME_PREVIEWS_PREFETCH,
            STYLE_LAYER_RASTER_FRAMES_PREFETCH,
        )

    qs = queryset if queryset is not None else Layer.objects.all()
    # This is for /layers/{layer_id} so we need to prefetch the frames and the default style
    return qs.select_related("dataset", "default_style").prefetch_related(
        LAYER_RASTER_FRAMES_PREFETCH,
        Prefetch(
            "default_style__frame_previews",
            queryset=RasterFramePreview.objects.select_related("layer_frame"),
        ),
    )
