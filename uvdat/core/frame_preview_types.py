from __future__ import annotations

from typing import TypedDict


class FramePreviewCorner(TypedDict):
    x: float
    y: float


class FramePreviewBounds(TypedDict, total=False):
    srs: str  # EPSG:4326
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    ul: FramePreviewCorner
    ur: FramePreviewCorner
    lr: FramePreviewCorner
    ll: FramePreviewCorner


class FramePreviewData(TypedDict):
    url: str  # presigned URL of the preview image
    width: int
    height: int
    bounds: FramePreviewBounds
