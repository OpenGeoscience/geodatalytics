from __future__ import annotations

from django.db.models import Case, CharField, Count, F, Prefetch, Q, QuerySet, Value, When

from uvdat.core.models import Layer, LayerFrame, LayerStyle, RasterFramePreview
from uvdat.core.models.frame_preview import PreviewStatus

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


def _preview_status_case() -> Case:
    return Case(
        When(_raster_frame_count__lte=1, then=Value(None, output_field=CharField(null=True))),
        When(
            _complete_with_image_count=F("_raster_frame_count"),
            then=Value("ready"),
        ),
        default=Value("notready"),
        output_field=CharField(null=True),
    )


def _annotate_layer_style_preview_counts(queryset: QuerySet) -> QuerySet:
    return queryset.annotate(
        _raster_frame_count=Count(
            "layer__frames",
            filter=Q(layer__frames__raster__isnull=False),
            distinct=True,
        ),
        _complete_with_image_count=Count(
            "frame_previews",
            filter=Q(
                frame_previews__status=PreviewStatus.COMPLETE,
                frame_previews__image__isnull=False,
            )
            & ~Q(frame_previews__image=""),
            distinct=True,
        ),
    )


def _annotate_layer_preview_counts(queryset: QuerySet) -> QuerySet:
    return queryset.annotate(
        _raster_frame_count=Count(
            "frames",
            filter=Q(frames__raster__isnull=False),
            distinct=True,
        ),
        _complete_with_image_count=Count(
            "default_style__frame_previews",
            filter=Q(
                default_style__frame_previews__status=PreviewStatus.COMPLETE,
                default_style__frame_previews__image__isnull=False,
            )
            & ~Q(default_style__frame_previews__image=""),
            distinct=True,
        ),
    )


def annotate_layer_style_preview_status(queryset: QuerySet) -> QuerySet:
    return _annotate_layer_style_preview_counts(queryset).annotate(
        preview_status=_preview_status_case(),
    )


def annotate_layer_preview_status(queryset: QuerySet) -> QuerySet:
    return _annotate_layer_preview_counts(queryset).annotate(
        preview_status=Case(
            When(
                default_style_id__isnull=True, then=Value(None, output_field=CharField(null=True))
            ),
            default=_preview_status_case(),
            output_field=CharField(null=True),
        ),
    )


def layer_queryset_with_previews(
    queryset: QuerySet | None = None,
    *,
    for_layer_style: bool = False,
) -> QuerySet:
    # This is for /layer-styles/?layer={layer_id} so we need to prefetch the frames for all styles
    if for_layer_style:
        qs = queryset if queryset is not None else LayerStyle.objects.all()
        return annotate_layer_style_preview_status(
            qs.select_related("layer", "layer__default_style").prefetch_related(
                FRAME_PREVIEWS_PREFETCH,
                STYLE_LAYER_RASTER_FRAMES_PREFETCH,
            )
        )

    qs = queryset if queryset is not None else Layer.objects.all()
    # This is for /layers/{layer_id} so we need to prefetch the frames and the default style
    return annotate_layer_preview_status(
        qs.select_related("dataset", "default_style").prefetch_related(
            LAYER_RASTER_FRAMES_PREFETCH,
            Prefetch(
                "default_style__frame_previews",
                queryset=RasterFramePreview.objects.select_related("layer_frame"),
            ),
        )
    )
