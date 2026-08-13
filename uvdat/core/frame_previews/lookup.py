from __future__ import annotations

from typing import TYPE_CHECKING

from uvdat.core.frame_previews.fingerprint import params_fingerprint, style_fingerprint
from uvdat.core.frame_previews.types import FramePreviewData
from uvdat.core.models.frame_preview import PreviewStatus, RasterFramePreview

if TYPE_CHECKING:
    from uvdat.core.models import Layer, LayerFrame


def serialize_frame_preview(preview: RasterFramePreview) -> FramePreviewData:
    return FramePreviewData(
        url=preview.image.url,
        width=preview.width,
        height=preview.height,
        bounds=preview.bounds,
    )


def previews_by_frame_id(
    frames: list[LayerFrame],
    fingerprint: str,
) -> dict[int, RasterFramePreview]:
    """Return ``{frame_id: RasterFramePreview}`` for ``fingerprint``."""
    if not frames:
        return {}
    return {
        preview.layer_frame_id: preview
        for preview in RasterFramePreview.objects.filter(
            layer_frame_id__in=[frame.id for frame in frames],
            style_fingerprint=fingerprint,
        )
    }


def ordered_complete_previews(
    layer: Layer,
    fingerprint: str,
) -> list[FramePreviewData] | None:
    """Return serialized previews in frame order, or None if any frame is incomplete."""
    if not layer.is_multiframe_raster():
        return None

    frames = layer.raster_frames()
    by_frame = previews_by_frame_id(frames, fingerprint)
    ordered = [by_frame.get(frame.id) for frame in frames]
    if not all(
        preview is not None and preview.status == PreviewStatus.COMPLETE and preview.image
        for preview in ordered
    ):
        return None
    return [serialize_frame_preview(preview) for preview in ordered]


def preview_status_for_fingerprint(
    layer: Layer,
    fingerprint: str,
) -> str | None:
    if not layer.is_multiframe_raster():
        return None

    frames = layer.raster_frames()
    by_frame = previews_by_frame_id(frames, fingerprint)
    if all(
        (preview := by_frame.get(frame.id))
        and preview.status == PreviewStatus.COMPLETE
        and preview.image
        for frame in frames
    ):
        return "ready"
    return "notready"


def previews_current_for_fingerprint(layer: Layer, fingerprint: str) -> bool:
    """Return whether every frame already has a complete preview for this fingerprint."""
    return preview_status_for_fingerprint(layer, fingerprint) == "ready"


def layer_default_fingerprint(layer: Layer) -> str:
    """Fingerprint for layer-level default previews (default style params, else ``{}``)."""
    if layer.default_style_id is not None:
        return style_fingerprint(layer.default_style)
    return params_fingerprint({})


def layer_default_multiframe_previews(layer: Layer) -> list[FramePreviewData] | None:
    """Previews for the layer default fingerprint (default style params or ``{}``)."""
    return ordered_complete_previews(
        layer,
        layer_default_fingerprint(layer),
    )
