from __future__ import annotations

import hashlib
import json

from django.utils import timezone

from uvdat.core.models import LayerStyle, RasterFramePreview, TaskResult
from uvdat.core.models.frame_preview import PreviewStatus
from uvdat.core.tasks.frame_preview import generate_layer_style_previews


def style_fingerprint(layer_style: LayerStyle) -> str:
    payload = json.dumps(layer_style.repr_style_configs(), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


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


def invalidate_and_enqueue_previews(layer_style: LayerStyle) -> TaskResult | None:
    if not style_needs_previews(layer_style):
        return None

    fingerprint = style_fingerprint(layer_style)
    mark_previews_regenerating(layer_style, fingerprint)
    supersede_pending_preview_tasks(layer_style.id)

    result = TaskResult.objects.create(
        name=f"Frame previews: {layer_style.name}",
        task_type="frame_preview",
        project=layer_style.project,
        inputs={
            "layer_style_id": layer_style.id,
            "layer_id": layer_style.layer_id,
            "fingerprint": fingerprint,
        },
    )

    generate_layer_style_previews.delay(
        layer_style.id,
        fingerprint=fingerprint,
        result_id=result.id,
    )
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

    statuses = [
        previews_by_frame[frame.id].status for frame in frames if frame.id in previews_by_frame
    ]

    if any(
        status in (PreviewStatus.CREATING, PreviewStatus.REGENERATING) for status in statuses
    ) or any(status == PreviewStatus.COMPLETE for status in statuses):
        result = "generating"
    elif any(status == PreviewStatus.FAILED for status in statuses):
        result = "failed"
    else:
        result = "none"
    return result
