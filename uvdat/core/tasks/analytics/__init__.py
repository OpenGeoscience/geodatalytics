from __future__ import annotations

from typing import TYPE_CHECKING

from .create_road_network import CreateRoadNetwork
from .flood_network_failure import FloodNetworkFailure
from .flood_simulation import FloodSimulation
from .geoai_segmentation import GeoAISegmentation
from .imagery_ask_qwen import ImageryAskQwen
from .network_recovery import NetworkRecovery
from .uncertainty_quantification import UncertaintyQuantification

if TYPE_CHECKING:
    from .analysis_type import AnalysisType

analysis_types: list[type[AnalysisType]] = [
    FloodSimulation,
    FloodNetworkFailure,
    ImageryAskQwen,
    NetworkRecovery,
    UncertaintyQuantification,
    GeoAISegmentation,
    CreateRoadNetwork,
]

__all__ = [analysis_type.__name__ for analysis_type in analysis_types]
