from __future__ import annotations

from dataclasses import dataclass
import io
import json
import logging
import time
from typing import TYPE_CHECKING, Any

from celery import shared_task
from django.core.files.base import ContentFile
from django_large_image import tilesource, utilities
from PIL import Image

from uvdat.core.frame_previews.fingerprint import style_fingerprint
from uvdat.core.frame_previews.raster_style import (
    apply_source_filters_to_style_query,
    build_raster_tiles_style_query,
    raster_source_filter_kwargs,
)
from uvdat.core.models import (
    Colormap,
    Layer,
    LayerStyle,
    Project,
    RasterData,
    RasterFramePreview,
    TaskResult,
)
from uvdat.core.models.frame_preview import PreviewStatus

if TYPE_CHECKING:
    from uvdat.core.frame_previews.types import FramePreviewBounds

"""Celery tasks and helpers for multiframe raster frame preview images.

Previews are styled PNG thumbnails stored on ``RasterFramePreview`` rows. They
let the frontend show a fast full-frame image before tile loading during frame
scrubbing. Generation is keyed by a style fingerprint so rapid successive style
saves do not publish stale images from an older task run.
"""

logger = logging.getLogger(__name__)

# Thumbnail sizing: default to 1/8 of FRAME_PREVIEW_MAX_PX (512px), but never
# below FRAME_PREVIEW_MIN_PX when the source raster is large enough to allow it.
FRAME_PREVIEW_MAX_PX = 4096
FRAME_PREVIEW_MIN_PX = 1024
FRAME_PREVIEW_DEFAULT_RESOLUTION_FRACTION = 1 / 8

# Applied when ingest creates a default style for a new multiframe raster layer.
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

    layer_style: LayerStyle
    fingerprint: str
    base_style_query: dict[str, Any]
    resolution_fraction: float | None = None

    @property
    def layer_style_id(self) -> int:
        return self.layer_style.id


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


def _colormaps_for_style(layer_style: LayerStyle) -> dict[int, Colormap]:
    colormaps = Colormap.objects.filter(project=layer_style.project) | Colormap.objects.filter(
        project__isnull=True
    )
    return {colormap.id: colormap for colormap in colormaps}


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


def ensure_default_layer_style(layer: Layer, project: Project) -> LayerStyle:
    """Return the project's Default style for a layer, creating it on ingest if needed."""
    style = LayerStyle.objects.filter(layer=layer, project=project, name="Default").first()
    if style is None:
        style = LayerStyle.objects.create(name="Default", layer=layer, project=project)
        style.save_style_configs(DEFAULT_MULTIFRAME_RASTER_STYLE_SPEC)
    if layer.default_style_id is None:
        layer.default_style = style
        layer.save(update_fields=["default_style"])
    return style


def _fingerprint_matches(layer_style: LayerStyle, fingerprint: str) -> bool:
    """Return whether the style's current configs still match the task fingerprint.

    ``repr_style_configs`` always reads from the database, so this detects a
    style save that happened after this task was enqueued.
    """
    return style_fingerprint(layer_style) == fingerprint


def _open_task_result(result_id: int | None, layer_style_id: int) -> TaskResult | None:
    """Load the TaskResult for this run, or None if it was already superseded."""
    if result_id is None:
        return None

    result = TaskResult.objects.filter(id=result_id).first()
    if result is None or result.completed is not None:
        logger.info(
            "Skipping preview generation for style=%s; task result %s already closed",
            layer_style_id,
            result_id,
        )
        return None
    return result


def _save_frame_preview(
    preview: RasterFramePreview,
    layer_style_id: int,
    frame_index: int,
    image: _FramePreviewImage,
) -> None:
    """Persist a generated preview and mark the row complete (API-servable)."""
    preview.width = image.width
    preview.height = image.height
    preview.bounds = image.bounds or {}
    preview.status = PreviewStatus.COMPLETE
    preview.image.save(
        f"frame-previews/{layer_style_id}/{frame_index}.png",
        ContentFile(image.png_bytes),
        save=False,
    )
    preview.save()


def _mark_frame_preview_failed(
    preview: RasterFramePreview,
    layer_style: LayerStyle,
    fingerprint: str,
) -> None:
    """Mark a row failed only when both the row and style still match this task."""
    if preview.style_fingerprint == fingerprint and _fingerprint_matches(layer_style, fingerprint):
        preview.status = PreviewStatus.FAILED
        preview.save(update_fields=["status"])


def _process_frame_preview(ctx: _PreviewGenerationContext, frame) -> str:
    """Generate one frame preview.

    Returns ``ready``, ``failed``, ``skipped``, or ``superseded``. A superseded
    outcome means a newer style save arrived and this task must stop writing.
    """
    if not _fingerprint_matches(ctx.layer_style, ctx.fingerprint):
        return "superseded"

    try:
        preview = RasterFramePreview.objects.get(
            layer_style=ctx.layer_style,
            layer_frame=frame,
        )
    except RasterFramePreview.DoesNotExist:
        logger.warning(
            "Missing preview row for style=%s frame=%s; skipping",
            ctx.layer_style_id,
            frame.id,
        )
        return "skipped"

    # Row fingerprint is set on enqueue; skip frames already claimed by a newer save.
    if preview.style_fingerprint != ctx.fingerprint:
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
            "Failed to generate frame preview for style=%s frame=%s",
            ctx.layer_style_id,
            frame.id,
        )
        _mark_frame_preview_failed(preview, ctx.layer_style, ctx.fingerprint)
        return "failed"

    # PNG generation is expensive; re-check before writing to storage.
    if not _fingerprint_matches(ctx.layer_style, ctx.fingerprint):
        return "superseded"

    _save_frame_preview(
        preview,
        ctx.layer_style_id,
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
    if not _fingerprint_matches(ctx.layer_style, ctx.fingerprint):
        logger.info(
            "Skipping task completion for style=%s; style superseded after loop",
            ctx.layer_style_id,
        )
        return

    if result is None:
        return

    result.write_outputs(
        {
            "layer_style_id": ctx.layer_style_id,
            "layer_id": ctx.layer_style.layer_id,
            "fingerprint": ctx.fingerprint,
            "ready_count": stats.ready_count,
            "failed_count": stats.failed_count,
        }
    )
    result.complete()


@shared_task
def generate_layer_style_previews(
    layer_style_id: int,
    fingerprint: str,
    result_id: int | None = None,
    resolution_fraction: float | None = None,
):
    """Generate styled PNG previews for every frame in a multiframe raster style.

    Enqueued by ``invalidate_and_enqueue_previews`` after a style save or ingest.
    Preview rows are created upstream with ``creating``/``regenerating`` status and
    cleared images; this task fills them in and sets ``complete`` or ``failed``.

    ``fingerprint`` is a sha256 of ``repr_style_configs()`` at enqueue time. The
    task aborts whenever the live style no longer matches, so rapid double-saves
    only publish previews for the latest style version.
    """
    started = time.perf_counter()
    layer_style = LayerStyle.objects.select_related("layer", "project").get(id=layer_style_id)
    frames = layer_style.layer.multiframe_raster_frames()
    if len(frames) <= 1:
        return

    if not _fingerprint_matches(layer_style, fingerprint):
        logger.info(
            "Skipping superseded preview generation for style=%s",
            layer_style_id,
        )
        return

    result = _open_task_result(result_id, layer_style_id)
    if result_id is not None and result is None:
        return

    logger.info(
        "Generating %d multiframe raster previews for style=%s layer=%r",
        len(frames),
        layer_style_id,
        layer_style.layer.name,
    )

    style_spec = layer_style.repr_style_configs()
    colormaps_by_id = _colormaps_for_style(layer_style)
    ctx = _PreviewGenerationContext(
        layer_style=layer_style,
        fingerprint=fingerprint,
        base_style_query=build_raster_tiles_style_query(style_spec, colormaps_by_id),
        resolution_fraction=resolution_fraction,
    )

    ready_count = 0
    failed_count = 0
    for frame in frames:
        outcome = _process_frame_preview(ctx, frame)
        if outcome == "superseded":
            logger.info(
                "Aborting preview generation for style=%s; style superseded",
                layer_style_id,
            )
            return
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
        "Multiframe raster previews for style=%s layer=%r: %d ready, %d failed in %.2fs",
        layer_style_id,
        layer_style.layer.name,
        ready_count,
        failed_count,
        time.perf_counter() - started,
    )
