from __future__ import annotations

from django.utils import timezone

from uvdat.core.frame_previews.fingerprint import style_fingerprint
from uvdat.core.models import Layer, LayerStyle, RasterFramePreview, TaskResult
from uvdat.core.models.frame_preview import PreviewStatus
from uvdat.core.tasks.frame_preview import generate_layer_style_previews


def style_needs_previews(layer_style: LayerStyle) -> bool:
    return layer_style.layer.is_multiframe_raster()


def supersede_pending_preview_tasks(layer_style_id: int) -> None:
    TaskResult.objects.filter(
        task_type="frame_preview",
        completed__isnull=True,
        inputs__layer_style_id=layer_style_id,
    ).update(
        completed=timezone.now(),
        status="Superseded by newer style save.",
    )


def previews_current_for_fingerprint(layer_style: LayerStyle, fingerprint: str) -> bool:
    """Return whether every frame already has a complete preview for this fingerprint."""
    frames = layer_style.layer.multiframe_raster_frames()
    if not frames:
        return False

    previews_by_frame = {
        preview.layer_frame_id: preview for preview in layer_style.frame_previews.all()
    }

    return all(
        (preview := previews_by_frame.get(frame.id))
        and preview.status == PreviewStatus.COMPLETE
        and preview.image
        and preview.style_fingerprint == fingerprint
        for frame in frames
    )


def clear_style_preview_instance_cache(layer_style: LayerStyle) -> None:
    """Drop queryset annotations and prefetches that go stale after invalidation."""
    layer_style.refresh_from_db()
    layer_style.__dict__.pop("preview_status", None)
    layer_style.__dict__.pop("_raster_frame_count", None)
    layer_style.__dict__.pop("_complete_with_image_count", None)
    if cache := getattr(layer_style, "_prefetched_objects_cache", None):
        cache.pop("frame_previews", None)


def mark_previews_regenerating(layer_style: LayerStyle, fingerprint: str) -> list[int]:
    """Upsert one preview row per multiframe frame and clear stale images."""
    frame_ids = []
    for frame in layer_style.layer.multiframe_raster_frames():
        preview, created = RasterFramePreview.objects.get_or_create(
            layer_style=layer_style,
            layer_frame=frame,
            defaults={
                "status": PreviewStatus.CREATING,
                "style_fingerprint": fingerprint,
            },
        )
        preview.style_fingerprint = fingerprint
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


def invalidate_and_enqueue_previews(
    layer_style: LayerStyle,
    *,
    asynchronous: bool = True,
) -> TaskResult | None:
    if not style_needs_previews(layer_style):
        return None

    layer_style.refresh_from_db()
    fingerprint = style_fingerprint(layer_style)
    if previews_current_for_fingerprint(layer_style, fingerprint):
        return None

    mark_previews_regenerating(layer_style, fingerprint)
    clear_style_preview_instance_cache(layer_style)
    supersede_pending_preview_tasks(layer_style.id)

    result = TaskResult.objects.create(
        name=f"Frame previews: {layer_style.layer.name} - {layer_style.name}",
        task_type="frame_preview",
        project=layer_style.project,
        inputs={
            "layer_style_id": layer_style.id,
            "layer_id": layer_style.layer_id,
            "layer_name": layer_style.layer.name,
            "fingerprint": fingerprint,
        },
    )

    if asynchronous:
        generate_layer_style_previews.delay(layer_style.id, fingerprint, result.id)
    else:
        generate_layer_style_previews.apply(args=(layer_style.id, fingerprint, result.id))
    return result


def preview_status_for_style(layer_style: LayerStyle) -> str | None:
    """Aggregate per-frame preview rows into a style-level status string."""
    if not style_needs_previews(layer_style):
        return None

    frames = layer_style.layer.multiframe_raster_frames()
    if not frames:
        return None

    previews_by_frame = {
        preview.layer_frame_id: preview for preview in layer_style.frame_previews.all()
    }

    if all(
        (preview := previews_by_frame.get(frame.id))
        and preview.status == PreviewStatus.COMPLETE
        and preview.image
        for frame in frames
    ):
        return "ready"

    return "notready"


def get_layer_style_preview_status(layer_style: LayerStyle) -> str | None:
    if "preview_status" in layer_style.__dict__:
        return layer_style.preview_status
    return preview_status_for_style(layer_style)


def get_layer_preview_status(layer: Layer) -> str | None:
    if "preview_status" in layer.__dict__:
        return layer.preview_status
    if layer.default_style_id is None:
        return None
    return get_layer_style_preview_status(layer.default_style)
