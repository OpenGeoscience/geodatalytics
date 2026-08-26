from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models import Count, Q, QuerySet

from uvdat.core.frame_previews.fingerprint import params_fingerprint
from uvdat.core.frame_previews.lookup import preview_status_for_fingerprint
from uvdat.core.frame_previews.preview_regeneration import (
    invalidate_and_enqueue_layer_previews,
    pending_preview_task,
)
from uvdat.core.models import Colormap, Layer, LayerStyle, Project
from uvdat.core.rest.querysets import layer_queryset_with_previews
from uvdat.core.tasks.run_mode import TaskRunMode

if TYPE_CHECKING:
    from collections.abc import Callable

RASTER_SOURCE_FILTER_KEYS = frozenset({"frame", "band"})


def _color_query_from_spec(
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
            color_query["palette"] = [marker["color"] for marker in colormap.markers]
    elif color_spec.get("single_color"):
        color_query["palette"] = color_spec["single_color"]
    return color_query


def _build_raster_style_params(
    style_spec: dict[str, Any],
    colormaps_by_id: dict[int, Colormap],
) -> dict[str, Any]:
    """Build django-large-image style JSON from style_spec (mirrors client getRasterTilesQuery)."""
    query: dict[str, Any] = {}
    for color_spec in style_spec.get("colors", []):
        color_query = _color_query_from_spec(color_spec, colormaps_by_id)
        if not color_spec.get("visible"):
            continue
        if color_spec.get("name") == "all":
            query = color_query
        elif color_query:
            query.setdefault("bands", [])
            color_query["band"] = color_spec["name"].replace("Band ", "")
            query["bands"].append(color_query)

    for filter_spec in style_spec.get("filters", []):
        if (
            filter_spec.get("include")
            and filter_spec.get("filter_by")
            and filter_spec.get("list")
            and len(filter_spec["list"]) == 1
            and filter_spec["filter_by"] not in RASTER_SOURCE_FILTER_KEYS
        ):
            query[filter_spec["filter_by"]] = filter_spec["list"][0]

    return query


def resolve_raster_style_params(layer_style: LayerStyle) -> tuple[dict[str, Any], bool] | None:
    """Return (params, reconstructed), or None when a referenced colormap is missing."""
    if layer_style.raster_style_params is not None:
        return dict(layer_style.raster_style_params), False

    style_spec = layer_style.repr_style_configs()
    colormap_ids = {
        color_spec["colormap"]["id"]
        for color_spec in style_spec.get("colors", [])
        if color_spec.get("colormap", {}).get("id")
    }
    colormaps_by_id = {
        colormap.id: colormap for colormap in Colormap.objects.filter(id__in=colormap_ids)
    }
    if colormap_ids - colormaps_by_id.keys():
        return None

    return _build_raster_style_params(style_spec, colormaps_by_id), True


def multiframe_layers_qs(
    *,
    layer_id: int | None = None,
    dataset_id: int | None = None,
    project_id: int | None = None,
) -> QuerySet:
    qs = (
        layer_queryset_with_previews()
        .annotate(raster_frame_count=Count("frames", filter=Q(frames__raster__isnull=False)))
        .filter(raster_frame_count__gt=1)
    )
    if layer_id is not None:
        qs = qs.filter(id=layer_id)
    if dataset_id is not None:
        qs = qs.filter(dataset_id=dataset_id)
    if project_id is not None:
        project = Project.objects.filter(id=project_id).first()
        if project is None:
            return qs.none()
        qs = qs.filter(dataset__in=project.datasets.all())
    return qs.order_by("id")


def _needs_generate(layer: Layer, params: dict[str, Any]) -> bool:
    fingerprint = params_fingerprint(params)
    if preview_status_for_fingerprint(layer, fingerprint) == "ready":
        return False
    return pending_preview_task(layer_id=layer.id, fingerprint=fingerprint) is None


def _collect_backfill_work(
    layer: Layer,
    *,
    project_id: int | None,
) -> list[tuple[dict[str, Any], LayerStyle | None]]:
    work: list[tuple[dict[str, Any], LayerStyle | None]] = []

    styles = LayerStyle.objects.filter(layer=layer).order_by("id")
    if project_id is not None:
        styles = styles.filter(project_id=project_id)

    for layer_style in styles:
        resolved = resolve_raster_style_params(layer_style)
        if resolved is None:
            continue

        params, reconstructed = resolved
        if reconstructed:
            layer_style.raster_style_params = params
            layer_style.save(update_fields=["raster_style_params"])
        work.append((params, layer_style))

    empty_fingerprint = params_fingerprint({})
    if _needs_generate(layer, {}) and not any(
        params_fingerprint(params) == empty_fingerprint for params, _ in work
    ):
        work.insert(0, ({}, None))

    return work


def _log_backfill_target(
    echo: Callable[[str], None],
    *,
    layer_style: LayerStyle | None,
) -> None:
    if layer_style is None:
        echo("  native RGB (no style params)")
    else:
        echo(f"  LayerStyle {layer_style.id} ({layer_style.name})")


def backfill_layer_previews(
    layer: Layer,
    *,
    project_id: int | None = None,
    echo: Callable[[str], None] | None = None,
) -> None:
    if not layer.is_multiframe_raster():
        return

    for params, layer_style in _collect_backfill_work(layer, project_id=project_id):
        if not _needs_generate(layer, params):
            continue
        if echo is not None:
            _log_backfill_target(echo, layer_style=layer_style)
        invalidate_and_enqueue_layer_previews(
            layer,
            params,
            run_mode=TaskRunMode.SYNC,
            layer_style=layer_style,
        )
