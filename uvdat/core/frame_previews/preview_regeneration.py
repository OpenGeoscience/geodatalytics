from __future__ import annotations

from typing import Any

from django.utils import timezone

from uvdat.core.frame_previews.fingerprint import params_fingerprint, style_fingerprint
from uvdat.core.frame_previews.lookup import (
    layer_default_fingerprint,
    preview_status_for_fingerprint,
    previews_by_frame_id,
)
from uvdat.core.models import Layer, LayerStyle, Project, RasterFramePreview, TaskResult
from uvdat.core.models.frame_preview import PreviewStatus
from uvdat.core.models.task_result import suppress_task_notifications


def layer_needs_previews(layer: Layer) -> bool:
    return layer.is_multiframe_raster()


def style_needs_previews(layer_style: LayerStyle) -> bool:
    return layer_needs_previews(layer_style.layer)


def _pending_preview_tasks_to_supersede(
    *,
    layer_id: int,
    fingerprint: str,
    layer_style_id: int | None = None,
) -> list[TaskResult]:
    """Select in-flight preview tasks that a newer enqueue should replace.

    Style-scoped enqueues supersede that style's pending tasks and any
    layer-default (no ``layer_style_id``) tasks for the same layer, so conversion
    and style regeneration cannot race on the same frames. Layer-default enqueues
    supersede other layer-default tasks with the same fingerprint.
    """
    candidates = TaskResult.objects.filter(
        task_type="frame_preview",
        completed__isnull=True,
        inputs__layer_id=layer_id,
    )
    to_supersede: list[TaskResult] = []
    for task in candidates:
        inputs = task.inputs or {}
        task_style_id = inputs.get("layer_style_id")
        if layer_style_id is not None:
            if task_style_id == layer_style_id or task_style_id is None:
                to_supersede.append(task)
        elif task_style_id is None and inputs.get("fingerprint") == fingerprint:
            to_supersede.append(task)
    return to_supersede


def supersede_pending_preview_tasks(
    *,
    layer_id: int,
    fingerprint: str,
    layer_style_id: int | None = None,
) -> None:
    """Close in-flight preview tasks superseded by a newer enqueue and revoke Celery."""
    pending = _pending_preview_tasks_to_supersede(
        layer_id=layer_id,
        fingerprint=fingerprint,
        layer_style_id=layer_style_id,
    )
    if not pending:
        return

    celery_task_ids = [
        celery_id
        for task in pending
        if isinstance((celery_id := (task.inputs or {}).get("celery_task_id")), str)
    ]
    TaskResult.objects.filter(
        id__in=[task.id for task in pending],
        completed__isnull=True,
    ).update(
        completed=timezone.now(),
        status="Superseded by newer preview request.",
    )

    if not celery_task_ids:
        return

    # Lazy import: avoid tasks <-> preview_regeneration cycle at module load.
    from uvdat.core.tasks.frame_preview import generate_frame_previews  # noqa: PLC0415

    for celery_task_id in celery_task_ids:
        generate_frame_previews.AsyncResult(celery_task_id).revoke(terminate=False)


def previews_current_for_fingerprint(layer: Layer, fingerprint: str) -> bool:
    """Return whether every frame already has a complete preview for this fingerprint."""
    frames = layer.raster_frames()
    if len(frames) <= 1:
        return False

    by_frame = previews_by_frame_id(frames, fingerprint)
    return all(
        (preview := by_frame.get(frame.id))
        and preview.status == PreviewStatus.COMPLETE
        and preview.image
        and preview.style_fingerprint == fingerprint
        for frame in frames
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


def invalidate_and_enqueue_layer_previews(
    layer: Layer,
    raster_style_params: dict[str, Any] | None = None,
    *,
    asynchronous: bool = True,
    project=None,
    layer_style: LayerStyle | None = None,
) -> TaskResult | None:
    """Invalidate/create preview rows for a params fingerprint and enqueue generation."""
    if not layer_needs_previews(layer):
        return None

    params = dict(raster_style_params or {})
    fingerprint = params_fingerprint(params)
    if previews_current_for_fingerprint(layer, fingerprint):
        return None

    mark_previews_regenerating(layer, fingerprint, params)
    clear_layer_preview_instance_cache(layer)
    if layer_style is not None:
        clear_style_preview_instance_cache(layer_style)

    style_name = layer_style.name if layer_style is not None else "default"
    supersede_pending_preview_tasks(
        layer_id=layer.id,
        fingerprint=fingerprint,
        layer_style_id=layer_style.id if layer_style is not None else None,
    )

    task_project = project
    if task_project is None and layer_style is not None:
        task_project = layer_style.project
    if task_project is None:
        # Prefer a project that already includes this dataset so the analytics
        # WebSocket (project-scoped) receives completion. Conversion-time tasks
        # before a project link still fall back to the conversion channel.
        task_project = Project.objects.filter(datasets=layer.dataset_id).first()

    inputs: dict[str, Any] = {
        "layer_id": layer.id,
        "layer_name": layer.name,
        "dataset_id": layer.dataset_id,
        "fingerprint": fingerprint,
    }
    if layer_style is not None:
        inputs["layer_style_id"] = layer_style.id

    result = TaskResult.objects.create(
        name=f"Frame previews: {layer.name} - {style_name}",
        task_type="frame_preview",
        project=task_project,
        inputs=inputs,
    )

    task_kwargs: dict[str, Any] = {}
    if layer_style is not None:
        task_kwargs["layer_style_id"] = layer_style.id

    # Lazy: preview_regeneration <- tasks.frame_preview <- tasks.__init__ <- tasks.dataset
    # <- preview_regeneration when dataset imports this module at top level.
    from uvdat.core.tasks.frame_preview import generate_frame_previews  # noqa: PLC0415

    if asynchronous:
        async_result = generate_frame_previews.delay(
            layer.id, fingerprint, params, result.id, **task_kwargs
        )
        celery_task_id = getattr(async_result, "id", None)
        if isinstance(celery_task_id, str):
            inputs["celery_task_id"] = celery_task_id
            result.inputs = inputs
            result.save(update_fields=["inputs"])
    else:
        with suppress_task_notifications():
            generate_frame_previews.apply(
                args=(layer.id, fingerprint, params, result.id),
                kwargs=task_kwargs,
            )
    return result


def invalidate_and_enqueue_previews(
    layer_style: LayerStyle,
    *,
    asynchronous: bool = True,
) -> TaskResult | None:
    """Invalidate previews for a style's current ``raster_style_params`` and enqueue."""
    if not style_needs_previews(layer_style):
        return None

    layer_style.refresh_from_db()
    return invalidate_and_enqueue_layer_previews(
        layer_style.layer,
        layer_style.raster_style_params,
        asynchronous=asynchronous,
        project=layer_style.project,
        layer_style=layer_style,
    )


def preview_status_for_style(layer_style: LayerStyle) -> str | None:
    if not style_needs_previews(layer_style):
        return None
    frames = layer_style.layer.raster_frames()
    return preview_status_for_fingerprint(frames, style_fingerprint(layer_style))


def get_layer_style_preview_status(layer_style: LayerStyle) -> str | None:
    if "preview_status" in layer_style.__dict__:
        return layer_style.preview_status
    return preview_status_for_style(layer_style)


def preview_status_for_layer(layer: Layer) -> str | None:
    if not layer_needs_previews(layer):
        return None
    frames = layer.raster_frames()
    return preview_status_for_fingerprint(frames, layer_default_fingerprint(layer))


def get_layer_preview_status(layer: Layer) -> str | None:
    if "preview_status" in layer.__dict__:
        return layer.preview_status
    return preview_status_for_layer(layer)
