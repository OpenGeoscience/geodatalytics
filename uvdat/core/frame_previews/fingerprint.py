from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from uvdat.core.models import LayerStyle


def _fingerprint_payload(params: dict[str, Any] | None) -> str:
    return json.dumps(params or {}, sort_keys=True, default=str)


def params_fingerprint(params: dict[str, Any] | None) -> str:
    """Sha256 of ``raster_style_params`` JSON used to render preview PNGs."""
    payload = _fingerprint_payload(params)
    return hashlib.sha256(payload.encode()).hexdigest()


def style_fingerprint(layer_style: LayerStyle) -> str:
    """Sha256 of a style's ``raster_style_params``."""
    return params_fingerprint(layer_style.raster_style_params)
