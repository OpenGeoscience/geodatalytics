from __future__ import annotations

from dataclasses import dataclass
import io
import json
import logging
import time
from typing import TYPE_CHECKING, Any

from celery import shared_task
from django.core.files.base import ContentFile
from django.utils import timezone
from django_large_image import tilesource, utilities
from PIL import Image

from uvdat.core.frame_previews.fingerprint import params_fingerprint
from uvdat.core.frame_previews.raster_style import (
    apply_source_filters_to_style_query,
    raster_source_filter_kwargs,
)
from uvdat.core.models import (
    Layer,
    LayerStyle,
    RasterData,
    RasterFramePreview,
    TaskResult,
)
from uvdat.core.models.frame_preview import PreviewStatus

if TYPE_CHECKING:
    from uvdat.core.frame_previews.types import FramePreviewBounds

"""Celery tasks and helpers for multiframe raster frame preview images.

Previews are styled PNG thumbnails stored on ``RasterFramePreview`` rows, keyed
by ``(layer_frame, style_fingerprint)``. Enqueue skips starting a second job
when one is already in flight for the same fingerprint.
"""

logger = logging.getLogger(__name__)

# Thumbnail sizing: default to 1/8 of FRAME_PREVIEW_MAX_PX (512px), but never
# below FRAME_PREVIEW_MIN_PX when the source raster is large enough to allow it.
FRAME_PREVIEW_MAX_PX = 4096
FRAME_PREVIEW_MIN_PX = 1024
FRAME_PREVIEW_DEFAULT_RESOLUTION_FRACTION = 1 / 8

# Applied when ingest/API still creates a Default LayerStyle for vector config.
DEFAULT_MULTIFRAME_RASTER_STYLE_SPEC = {
    "default_frame": 0,
    "opacity": 1,
    "colors": [{"name": "all", "visible": True, "use_feature_props": True}],
    "sizes": [{"name": "all", "zoom_scaling": True, "single_size": 5}],
    "filters": [],
}


@dataclass(frozen=True)
class _PreviewGenerationContext:
    """Immutable inputs shared across all frames in one task invocation."""

    layer: Layer
    fingerprint: str
    base_style_query: dict[str, Any]
    layer_style: LayerStyle | None = None
    resolution_fraction: float | None = None
    task_result: TaskResult | None = None

    @property
    def layer_id(self) -> int:
        return self.layer.id


@dataclass(frozen=True)
class _FramePreviewImage:
    """PNG payload and metadata produced by ``generate_frame_preview_png``."""

    png_bytes: bytes
    width: int
    height: int
    bounds: FramePreviewBounds | None


@dataclass(frozen=True)
class _PreviewGenerationStats:
    """Per-task frame counts written to ``TaskResult.outputs`` on completion."""

    ready_count: int
    failed_count: int


def resolve_resolution_fraction(resolution_fraction: float | None = None) -> float:
    if resolution_fraction is None:
        return FRAME_PREVIEW_DEFAULT_RESOLUTION_FRACTION
    return float(resolution_fraction)


def _raster_max_dimension(metadata: dict[str, Any]) -> int:
    size_x = metadata.get("sizeX") or metadata.get("width") or 0
    size_y = metadata.get("sizeY") or metadata.get("height") or 0
    return max(int(size_x), int(size_y))


def resolve_preview_max_dimension(
    resolution_fraction: float | None = None,
    raster_max_dimension: int | None = None,
) -> int:
    """Pick a thumbnail edge length, clamped to the source raster's size."""
    fraction = resolve_resolution_fraction(resolution_fraction)
    fractional = round(FRAME_PREVIEW_MAX_PX * fraction)
    if not raster_max_dimension or raster_max_dimension < 2:
        return max(2, fractional)
    # Small rasters use their native size; larger ones get at least MIN_PX.
    floor = min(raster_max_dimension, FRAME_PREVIEW_MIN_PX)
    return max(2, min(max(fractional, floor), raster_max_dimension))


def _thumbnail_png_bytes(thumb_data: Any) -> bytes:
    if isinstance(thumb_data, bytes):
        return thumb_data
    if isinstance(thumb_data, Image.Image):
        buffer = io.BytesIO()
        thumb_data.save(buffer, format="PNG")
        return buffer.getvalue()
    msg = f"Unsupported thumbnail data type: {type(thumb_data)!r}"
    raise TypeError(msg)


def _preview_bounds(source) -> FramePreviewBounds | None:
    bounds = tilesource.get_bounds(source, projection="EPSG:4326")
    if not bounds:
        return None
    result: FramePreviewBounds = {
        "srs": "EPSG:4326",
        "xmin": bounds["xmin"],
        "xmax": bounds["xmax"],
        "ymin": bounds["ymin"],
        "ymax": bounds["ymax"],
    }
    for corner in ("ul", "ur", "lr", "ll"):
        corner_bounds = bounds.get(corner)
        if corner_bounds:
            result[corner] = {"x": corner_bounds["x"], "y": corner_bounds["y"]}
    return result


def generate_frame_preview_png(
    raster: RasterData,
    source_filters: dict[str, Any] | None,
    base_style_query: dict[str, Any],
    resolution_fraction: float | None = None,
) -> tuple[bytes, int, int, FramePreviewBounds | None]:
    """Render one frame as a styled PNG via large-image.

    Frame selection is passed through ``source_filters`` (e.g. ``{"frame": 3}``),
    not embedded in the style query, so one style query can be reused for every
    frame in a multiframe layer.
    """
    style_query = apply_source_filters_to_style_query(base_style_query, source_filters)
    style = json.dumps(style_query) if style_query else None
    source_kwargs = raster_source_filter_kwargs(source_filters)
    raster_path = utilities.field_file_to_local_path(raster.cloud_optimized_geotiff)
    source = tilesource.get_tilesource_from_path(
        raster_path,
        encoding="PNG",
        style=style,
    )
    max_dimension = resolve_preview_max_dimension(
        resolution_fraction,
        _raster_max_dimension(source.getMetadata()),
    )
    thumb_data, _mime_type = source.getThumbnail(
        encoding="PNG",
        width=max_dimension,
        height=max_dimension,
        **source_kwargs,
    )
    png_bytes = _thumbnail_png_bytes(thumb_data)
    image = Image.open(io.BytesIO(png_bytes))
    return png_bytes, image.width, image.height, _preview_bounds(source)


def _abandon_task_result(result_id: int | None, status: str) -> None:
    """Close an open TaskResult without marking it successfully completed."""
    if result_id is None:
        return
    TaskResult.objects.filter(id=result_id, completed__isnull=True).update(
        completed=timezone.now(),
        status=status,
    )


def _open_task_result(result_id: int | None, layer_id: int) -> TaskResult | None:
    """Load the TaskResult for this run, or None if it is missing/already closed."""
    if result_id is None:
        return None

    result = TaskResult.objects.filter(id=result_id).first()
    if result is None or result.completed is not None:
        logger.info(
            "Skipping preview generation for layer=%s; task result %s already closed",
            layer_id,
            result_id,
        )
        return None
    return result


def _save_frame_preview(
    preview: RasterFramePreview,
    layer_id: int,
    fingerprint: str,
    frame_index: int,
    image: _FramePreviewImage,
) -> None:
    """Persist a generated preview and mark the row complete (API-servable)."""
    preview.width = image.width
    preview.height = image.height
    preview.bounds = image.bounds or {}
    preview.status = PreviewStatus.COMPLETE
    preview.image.save(
        f"frame-previews/{layer_id}/{fingerprint[:16]}/{frame_index}.png",
        ContentFile(image.png_bytes),
        save=False,
    )
    preview.save()


def _mark_frame_preview_failed(preview: RasterFramePreview, fingerprint: str) -> None:
    if preview.style_fingerprint == fingerprint:
        preview.status = PreviewStatus.FAILED
        preview.save(update_fields=["status"])


def _process_frame_preview(ctx: _PreviewGenerationContext, frame) -> str:
    """Generate one frame preview.

    Returns ``ready``, ``failed``, or ``skipped``.
    """
    try:
        preview = RasterFramePreview.objects.get(
            layer_frame=frame,
            style_fingerprint=ctx.fingerprint,
        )
    except RasterFramePreview.DoesNotExist:
        logger.warning(
            "Missing preview row for layer=%s fingerprint=%s frame=%s; skipping",
            ctx.layer_id,
            ctx.fingerprint[:8],
            frame.id,
        )
        return "skipped"

    try:
        png_bytes, width, height, bounds = generate_frame_preview_png(
            frame.raster,
            frame.source_filters,
            ctx.base_style_query,
            ctx.resolution_fraction,
        )
    except Exception:
        logger.exception(
            "Failed to generate frame preview for layer=%s frame=%s",
            ctx.layer_id,
            frame.id,
        )
        _mark_frame_preview_failed(preview, ctx.fingerprint)
        return "failed"

    _save_frame_preview(
        preview,
        ctx.layer_id,
        ctx.fingerprint,
        frame.index,
        _FramePreviewImage(png_bytes, width, height, bounds),
    )
    return "ready"


def _complete_preview_task(
    result: TaskResult | None,
    ctx: _PreviewGenerationContext,
    stats: _PreviewGenerationStats,
) -> None:
    """Finalize the TaskResult, which triggers a WebSocket notification."""
    if result is None:
        return

    result.refresh_from_db(fields=["completed"])
    if result.completed is not None:
        return

    result.outputs = {
        "layer_id": ctx.layer_id,
        "fingerprint": ctx.fingerprint,
        "ready_count": stats.ready_count,
        "failed_count": stats.failed_count,
        **({"layer_style_id": ctx.layer_style.id} if ctx.layer_style is not None else {}),
    }
    result.save(update_fields=["outputs"])
    result.complete()


def _resolve_preview_style_inputs(
    layer_id: int,
    fingerprint: str,
    base_style_query: dict[str, Any] | None,
    layer_style_id: int | None,
) -> tuple[LayerStyle | None, dict[str, Any]]:
    """Resolve render params from the enqueue snapshot; optionally attach a style."""
    query = dict(base_style_query or {})
    if params_fingerprint(query) != fingerprint:
        logger.warning(
            "base_style_query fingerprint mismatch for layer=%s; using provided query",
            layer_id,
        )

    layer_style = None
    if layer_style_id is not None:
        layer_style = LayerStyle.objects.filter(id=layer_style_id).first()
        if layer_style is None:
            logger.info(
                "Style %s missing for layer=%s; generating from enqueued params",
                layer_style_id,
                layer_id,
            )
    return layer_style, query


@shared_task
def generate_frame_previews(  # noqa: PLR0913
    layer_id: int,
    fingerprint: str,
    base_style_query: dict[str, Any] | None = None,
    result_id: int | None = None,
    layer_style_id: int | None = None,
    resolution_fraction: float | None = None,
):
    """Generate styled PNG previews for every frame of a multiframe raster layer.

    Rows are keyed by ``(layer_frame, fingerprint)`` and created upstream with
    ``creating``/``regenerating`` status. Rendering uses the snapshotted
    ``base_style_query`` from enqueue time.
    """
    started = time.perf_counter()
    layer = Layer.objects.get(id=layer_id)
    if not layer.is_multiframe_raster():
        _abandon_task_result(result_id, "Layer is not multiframe; nothing to preview.")
        return
    frames = layer.raster_frames()

    layer_style, query = _resolve_preview_style_inputs(
        layer_id,
        fingerprint,
        base_style_query,
        layer_style_id,
    )

    result = _open_task_result(result_id, layer_id)
    if result_id is not None and result is None:
        return

    logger.info(
        "Generating %d multiframe raster previews for layer=%r fingerprint=%s",
        len(frames),
        layer.name,
        fingerprint[:8],
    )

    ctx = _PreviewGenerationContext(
        layer=layer,
        fingerprint=fingerprint,
        base_style_query=query,
        layer_style=layer_style,
        resolution_fraction=resolution_fraction,
        task_result=result,
    )

    ready_count = 0
    failed_count = 0
    for frame in frames:
        outcome = _process_frame_preview(ctx, frame)
        if outcome == "ready":
            ready_count += 1
        elif outcome == "failed":
            failed_count += 1

    _complete_preview_task(
        result,
        ctx,
        _PreviewGenerationStats(ready_count, failed_count),
    )

    logger.info(
        "Multiframe raster previews for layer=%r: %d ready, %d failed in %.2fs",
        layer.name,
        ready_count,
        failed_count,
        time.perf_counter() - started,
    )
