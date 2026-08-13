from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import transaction

from uvdat.core.frame_previews.fingerprint import params_fingerprint, style_fingerprint
from uvdat.core.frame_previews.lookup import (
    layer_default_fingerprint,
    preview_status_for_fingerprint,
    previews_current_for_fingerprint,
)
from uvdat.core.models import Layer, LayerStyle, Project, RasterFramePreview, TaskResult
from uvdat.core.models.frame_preview import PreviewStatus
from uvdat.core.models.task_result import suppress_task_notifications

if TYPE_CHECKING:
    from uvdat.core.tasks.run_mode import TaskRunMode


def _coerce_run_mode(run_mode: TaskRunMode | str) -> TaskRunMode:
    # Lazy: this module is imported by tasks.dataset during package init.
    from uvdat.core.tasks.run_mode import TaskRunMode as _TaskRunMode  # noqa: PLC0415

    return _TaskRunMode(run_mode)


def layer_needs_previews(layer: Layer) -> bool:
    return layer.is_multiframe_raster()


def style_needs_previews(layer_style: LayerStyle) -> bool:
    return layer_needs_previews(layer_style.layer)


def pending_preview_task(*, layer_id: int, fingerprint: str) -> TaskResult | None:
    """Return an in-flight preview task for this layer fingerprint, if any."""
    return (
        TaskResult.objects.filter(
            task_type="frame_preview",
            completed__isnull=True,
            inputs__layer_id=layer_id,
            inputs__fingerprint=fingerprint,
        )
        .order_by("id")
        .first()
    )


def clear_layer_preview_instance_cache(layer: Layer) -> None:
    layer.__dict__.pop("preview_status", None)
    layer.__dict__.pop("_raster_frame_count", None)
    layer.__dict__.pop("_complete_with_image_count", None)
    layer.__dict__.pop("_raster_frames", None)
    if cache := getattr(layer, "_prefetched_objects_cache", None):
        cache.pop("frames", None)


def clear_style_preview_instance_cache(layer_style: LayerStyle) -> None:
    """Drop queryset annotations and prefetches that go stale after invalidation."""
    layer_style.refresh_from_db()
    layer_style.__dict__.pop("preview_status", None)
    layer_style.__dict__.pop("_raster_frame_count", None)
    layer_style.__dict__.pop("_complete_with_image_count", None)
    if cache := getattr(layer_style, "_prefetched_objects_cache", None):
        cache.pop("layer", None)
    clear_layer_preview_instance_cache(layer_style.layer)


def mark_previews_regenerating(
    layer: Layer,
    fingerprint: str,
    raster_style_params: dict[str, Any] | None,
) -> list[int]:
    """Upsert one preview row per multiframe frame for this fingerprint and clear images."""
    params = dict(raster_style_params or {})
    frame_ids = []
    for frame in layer.raster_frames():
        preview, created = RasterFramePreview.objects.get_or_create(
            layer_frame=frame,
            style_fingerprint=fingerprint,
            defaults={
                "status": PreviewStatus.CREATING,
                "raster_style_params": params,
            },
        )
        preview.raster_style_params = params
        preview.status = PreviewStatus.CREATING if created else PreviewStatus.REGENERATING

        if preview.image:
            preview.image.delete(save=False)
            preview.image = None
        preview.width = None
        preview.height = None
        preview.bounds = {}
        preview.save()
        frame_ids.append(frame.id)
    return frame_ids


def _resolve_preview_task_project(
    layer: Layer,
    project,
    layer_style: LayerStyle | None,
):
    if project is not None:
        return project
    if layer_style is not None:
        return layer_style.project
    # Prefer a project that already includes this dataset so the analytics
    # WebSocket (project-scoped) receives completion. Conversion-time tasks
    # before a project link still fall back to the conversion channel.
    return Project.objects.filter(datasets=layer.dataset_id).first()


def _dispatch_frame_preview_task(
    result: TaskResult,
    *,
    fingerprint: str,
    params: dict[str, Any],
    task_kwargs: dict[str, Any],
    run_mode: TaskRunMode | str,
) -> None:
    # Lazy: preview_regeneration <- tasks.frame_preview <- tasks.__init__ <- tasks.dataset
    # <- preview_regeneration when dataset imports this module at top level.
    from uvdat.core.tasks.frame_preview import generate_frame_previews  # noqa: PLC0415

    run_mode = _coerce_run_mode(run_mode)
    layer_id = result.inputs["layer_id"]
    result_id = result.id

    if run_mode == "async":
        # Defer until after the surrounding transaction commits so a worker
        # cannot start before preview rows / TaskResult / style params exist.
        enqueue_params = dict(params)
        enqueue_kwargs = dict(task_kwargs)

        def _enqueue_preview_task() -> None:
            generate_frame_previews.delay(
                layer_id,
                fingerprint,
                enqueue_params,
                result_id,
                **enqueue_kwargs,
            )

        transaction.on_commit(_enqueue_preview_task)
        return

    with suppress_task_notifications():
        generate_frame_previews.apply(
            args=(layer_id, fingerprint, params, result_id),
            kwargs=task_kwargs,
        )
        # Defer until after the surrounding transaction commits so a worker
        # cannot start before preview rows / TaskResult / style params exist.
        enqueue_params = dict(params)
        enqueue_kwargs = dict(task_kwargs)

        def _enqueue_preview_task() -> None:
            generate_frame_previews.delay(
                layer_id,
                fingerprint,
                enqueue_params,
                result_id,
                **enqueue_kwargs,
            )

        transaction.on_commit(_enqueue_preview_task)
        return

    with suppress_task_notifications():
        generate_frame_previews.apply(
            args=(layer_id, fingerprint, params, result_id),
            kwargs=task_kwargs,
        )


def invalidate_and_enqueue_layer_previews(
    layer: Layer,
    raster_style_params: dict[str, Any] | None = None,
    *,
    run_mode: TaskRunMode | str = "async",
    project=None,
    layer_style: LayerStyle | None = None,
) -> TaskResult | None:
    """Invalidate/create preview rows for a params fingerprint and enqueue generation.

    If previews are already complete, or a job for this fingerprint is already
    in flight, do not start another Celery task.
    """
    if not layer_needs_previews(layer):
        return None

    run_mode = _coerce_run_mode(run_mode)
    params = dict(raster_style_params or {})
    fingerprint = params_fingerprint(params)
    if previews_current_for_fingerprint(layer, fingerprint):
        return None

    existing = pending_preview_task(layer_id=layer.id, fingerprint=fingerprint)
    if existing is not None:
        return existing

    mark_previews_regenerating(layer, fingerprint, params)
    clear_layer_preview_instance_cache(layer)
    if layer_style is not None:
        clear_style_preview_instance_cache(layer_style)

    style_name = layer_style.name if layer_style is not None else "default"
    inputs: dict[str, Any] = {
        "layer_id": layer.id,
        "layer_name": layer.name,
        "dataset_id": layer.dataset_id,
        "fingerprint": fingerprint,
    }
    task_kwargs: dict[str, Any] = {}
    if layer_style is not None:
        inputs["layer_style_id"] = layer_style.id
        task_kwargs["layer_style_id"] = layer_style.id

    result = TaskResult.objects.create(
        name=f"Frame previews: {layer.name} - {style_name}",
        task_type="frame_preview",
        project=_resolve_preview_task_project(layer, project, layer_style),
        inputs=inputs,
    )
    _dispatch_frame_preview_task(
        result,
        fingerprint=fingerprint,
        params=params,
        task_kwargs=task_kwargs,
        run_mode=run_mode,
    )
    return result


def invalidate_and_enqueue_previews(
    layer_style: LayerStyle,
    *,
    run_mode: TaskRunMode | str = "async",
) -> TaskResult | None:
    """Invalidate previews for a style's current ``raster_style_params`` and enqueue."""
    if not style_needs_previews(layer_style):
        return None

    layer_style.refresh_from_db()
    return invalidate_and_enqueue_layer_previews(
        layer_style.layer,
        layer_style.raster_style_params,
        run_mode=run_mode,
        project=layer_style.project,
        layer_style=layer_style,
    )


def preview_status_for_style(layer_style: LayerStyle) -> str | None:
    if not style_needs_previews(layer_style):
        return None
    return preview_status_for_fingerprint(layer_style.layer, style_fingerprint(layer_style))


def get_layer_style_preview_status(layer_style: LayerStyle) -> str | None:
    if "preview_status" in layer_style.__dict__:
        return layer_style.preview_status
    return preview_status_for_style(layer_style)


def preview_status_for_layer(layer: Layer) -> str | None:
    if not layer_needs_previews(layer):
        return None
    return preview_status_for_fingerprint(layer, layer_default_fingerprint(layer))


def get_layer_preview_status(layer: Layer) -> str | None:
    if "preview_status" in layer.__dict__:
        return layer.preview_status
    return preview_status_for_layer(layer)
