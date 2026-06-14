from __future__ import annotations

import io
import json
import logging
import time
from typing import Any

from celery import shared_task
from django.core.files.base import ContentFile
from django_large_image import tilesource, utilities
from PIL import Image

from uvdat.core.models import (
    Colormap,
    Layer,
    LayerStyle,
    Project,
    RasterData,
    RasterFramePreview,
)
from uvdat.core.raster_style import (
    apply_source_filters_to_style_query,
    build_raster_tiles_style_query,
    raster_source_filter_kwargs,
)

logger = logging.getLogger(__name__)

FRAME_PREVIEW_MAX_PX = 4096
FRAME_PREVIEW_MIN_PX = 1024
FRAME_PREVIEW_DEFAULT_RESOLUTION_FRACTION = 1 / 8

DEFAULT_MULTIFRAME_RASTER_STYLE_SPEC = {
    "default_frame": 0,
    "opacity": 1,
    "colors": [{"name": "all", "visible": True, "use_feature_props": True}],
    "sizes": [{"name": "all", "zoom_scaling": True, "single_size": 5}],
    "filters": [],
}


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
    fraction = resolve_resolution_fraction(resolution_fraction)
    fractional = round(FRAME_PREVIEW_MAX_PX * fraction)
    if not raster_max_dimension or raster_max_dimension < 2:
        return max(2, fractional)
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


def _preview_bounds(source) -> dict[str, Any] | None:
    bounds = tilesource.get_bounds(source, projection="EPSG:4326")
    if not bounds:
        return None
    return {
        "srs": "EPSG:4326",
        "xmin": bounds["xmin"],
        "xmax": bounds["xmax"],
        "ymin": bounds["ymin"],
        "ymax": bounds["ymax"],
    }


def generate_frame_preview_png(
    raster: RasterData,
    source_filters: dict[str, Any] | None,
    base_style_query: dict[str, Any],
    resolution_fraction: float | None = None,
) -> tuple[bytes, int, int, dict[str, Any] | None]:
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
    style = LayerStyle.objects.filter(layer=layer, project=project, name="Default").first()
    if style is None:
        style = LayerStyle.objects.create(name="Default", layer=layer, project=project)
        style.save_style_configs(DEFAULT_MULTIFRAME_RASTER_STYLE_SPEC)
    if layer.default_style_id is None:
        layer.default_style = style
        layer.save(update_fields=["default_style"])
    return style


@shared_task
def generate_layer_style_previews(
    layer_style_id: int,
    resolution_fraction: float | None = None,
):
    started = time.perf_counter()
    layer_style = LayerStyle.objects.select_related("layer").get(id=layer_style_id)
    frames = layer_style.layer.multiframe_raster_frames()
    if len(frames) <= 1:
        return

    logger.info(
        "Generating %d multiframe raster previews for style=%s layer=%r",
        len(frames),
        layer_style_id,
        layer_style.layer.name,
    )

    style_spec = layer_style.repr_style_configs()
    colormaps_by_id = _colormaps_for_style(layer_style)
    base_style_query = build_raster_tiles_style_query(style_spec, colormaps_by_id)

    ready_count = 0
    failed_count = 0
    for frame in frames:
        try:
            png_bytes, width, height, bounds = generate_frame_preview_png(
                frame.raster,
                frame.source_filters,
                base_style_query,
                resolution_fraction,
            )
            preview, _created = RasterFramePreview.objects.update_or_create(
                layer_style=layer_style,
                layer_frame=frame,
                defaults={
                    "width": width,
                    "height": height,
                    "bounds": bounds or {},
                },
            )
            preview.image.save(
                f"frame-previews/{layer_style_id}/{frame.index}.png",
                ContentFile(png_bytes),
                save=True,
            )
            ready_count += 1
        except Exception:
            failed_count += 1
            logger.exception(
                "Failed to generate frame preview for style=%s frame=%s",
                layer_style_id,
                frame.id,
            )
    logger.info(
        "Multiframe raster previews for style=%s layer=%r: %d ready, %d failed in %.2fs",
        layer_style_id,
        layer_style.layer.name,
        ready_count,
        failed_count,
        time.perf_counter() - started,
    )
