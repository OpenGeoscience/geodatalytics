from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from uvdat.core.models import Colormap

RASTER_SOURCE_FILTER_KEYS = frozenset({"frame", "band"})


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _mix_marker_colors(
    marker_a: dict[str, Any],
    marker_b: dict[str, Any],
) -> dict[str, Any]:
    rgb_a = _hex_to_rgb(marker_a["color"])
    rgb_b = _hex_to_rgb(marker_b["color"])
    mixed = tuple((a + b) // 2 for a, b in zip(rgb_a, rgb_b, strict=True))
    return {
        "color": _rgb_to_hex(mixed),
        "value": (marker_a["value"] + marker_b["value"]) / 2,
    }


def colormap_markers_subsample(
    colormap: Colormap,
    applied_colormap: dict[str, Any],
    n: int | None = None,
) -> list[dict[str, Any]]:
    markers = list(colormap.markers)
    if n is None and applied_colormap.get("discrete") and applied_colormap.get("n_colors"):
        n = applied_colormap["n_colors"]
    if n and markers:
        while n > len(markers):
            expanded: list[dict[str, Any]] = []
            for i in range(len(markers) - 1):
                expanded.append(markers[i])
                expanded.append(_mix_marker_colors(markers[i], markers[i + 1]))
            expanded.append(markers[-1])
            markers = expanded
        total_items = len(markers) - 1
        interval = total_items // (n - 1) if n > 1 else 0
        elements = [markers[0]]
        elements.extend(markers[i * interval] for i in range(1, n - 1))
        elements.append(markers[-1])
        return elements
    return markers


def _build_color_query_from_spec(
    color_spec: dict[str, Any],
    colormaps_by_id: dict[int, Colormap],
) -> dict[str, Any]:
    color_query: dict[str, Any] = {}
    colormap_spec = color_spec.get("colormap")
    if colormap_spec:
        if colormap_spec.get("range"):
            color_query["min"] = colormap_spec["range"][0]
            color_query["max"] = colormap_spec["range"][1]
        if colormap_spec.get("discrete"):
            color_query["scheme"] = "discrete"
        if colormap_spec.get("clamp") is False:
            color_query["clamp"] = False
        colormap = colormaps_by_id.get(colormap_spec.get("id"))
        if colormap and colormap.markers:
            markers = colormap_markers_subsample(colormap, colormap_spec)
            color_query["palette"] = [marker["color"] for marker in markers]
    elif color_spec.get("single_color"):
        color_query["palette"] = color_spec["single_color"]
    return color_query


def _apply_color_spec_to_query(
    query: dict[str, Any],
    color_spec: dict[str, Any],
    color_query: dict[str, Any],
) -> dict[str, Any]:
    if not color_spec.get("visible"):
        return query
    if color_spec.get("name") == "all":
        return color_query
    query.setdefault("bands", [])
    color_query["band"] = color_spec["name"].replace("Band ", "")
    query["bands"].append(color_query)
    return query


def _apply_non_source_filters(
    query: dict[str, Any],
    style_spec: dict[str, Any],
) -> None:
    for filter_spec in style_spec.get("filters", []):
        if (
            filter_spec.get("include")
            and filter_spec.get("filter_by")
            and filter_spec.get("list")
            and len(filter_spec["list"]) == 1
            and filter_spec["filter_by"] not in RASTER_SOURCE_FILTER_KEYS
        ):
            query[filter_spec["filter_by"]] = filter_spec["list"][0]


def build_raster_tiles_style_query(
    style_spec: dict[str, Any],
    colormaps_by_id: dict[int, Colormap],
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    for color_spec in style_spec.get("colors", []):
        color_query = _build_color_query_from_spec(color_spec, colormaps_by_id)
        query = _apply_color_spec_to_query(query, color_spec, color_query)
    _apply_non_source_filters(query, style_spec)
    return query


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


def build_thumbnail_style_query(
    style_spec: dict[str, Any],
    source_filters: dict[str, Any] | None,
    colormaps_by_id: dict[int, Colormap],
) -> dict[str, Any]:
    return apply_source_filters_to_style_query(
        build_raster_tiles_style_query(style_spec, colormaps_by_id),
        source_filters,
    )
