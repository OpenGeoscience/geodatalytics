from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uvdat.core.models import LayerStyle


def style_fingerprint(layer_style: LayerStyle) -> str:
    payload = json.dumps(layer_style.repr_style_configs(), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()
