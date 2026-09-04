from __future__ import annotations

import json
from typing import Any

# Thumbnail PNGs need explicit nodata handling: large_image maps masked nodata to
# black RGB unless the style includes nodata (and, for native single-band rasters,
# a palette with alpha). This mirrors styled tile transparency without changing
# stored ``raster_style_params`` fingerprints.
_NATIVE_SINGLE_BAND_PREVIEW_STYLE: dict[str, Any] = {
    "nodata": "auto",
    "min": "auto",
    "max": "auto",
    "palette": ["#00000000", "#ffffff"],
}


def apply_source_filters_to_style_query(
    base_query: dict[str, Any],
    source_filters: dict[str, Any] | None,
) -> dict[str, Any]:
    query = dict(base_query)
    if source_filters and "band" in source_filters:
        query["band"] = source_filters["band"]
    return query


def raster_source_filter_kwargs(source_filters: dict[str, Any] | None) -> dict[str, Any]:
    """Return large_image kwargs that must not be embedded in style JSON."""
    if not source_filters or "frame" not in source_filters:
        return {}
    return {"frame": source_filters["frame"]}


def ensure_nodata_in_style_query(style_query: dict[str, Any]) -> dict[str, Any]:
    """Ensure styled preview renders nodata as transparent PNG alpha, not black."""
    query = dict(style_query)
    bands = query.get("bands")
    if isinstance(bands, list):
        query["bands"] = [
            {**band, "nodata": band.get("nodata", "auto")} if isinstance(band, dict) else band
            for band in bands
        ]
    elif "nodata" not in query:
        query["nodata"] = "auto"
    return query


def resolve_preview_style_json(
    base_style_query: dict[str, Any],
    source_filters: dict[str, Any] | None,
    *,
    band_count: int | None,
) -> str | None:
    """Build large-image style JSON for one preview frame."""
    style_query = apply_source_filters_to_style_query(base_style_query, source_filters)
    if style_query:
        return json.dumps(ensure_nodata_in_style_query(style_query))
    if band_count == 1:
        return json.dumps(dict(_NATIVE_SINGLE_BAND_PREVIEW_STYLE))
    return None
