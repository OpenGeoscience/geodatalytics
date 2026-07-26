from __future__ import annotations

from typing import Any


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
