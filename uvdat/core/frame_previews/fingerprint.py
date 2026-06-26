from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uvdat.core.models import LayerStyle


def _fingerprint_payload(configs: dict) -> str:
    normalized = dict(configs)
    normalized["default_frame"] = int(normalized["default_frame"])
    normalized["opacity"] = float(normalized["opacity"])
    return json.dumps(normalized, sort_keys=True, default=str)


def style_fingerprint(layer_style: LayerStyle) -> str:
    payload = _fingerprint_payload(layer_style.repr_style_configs())
    return hashlib.sha256(payload.encode()).hexdigest()
