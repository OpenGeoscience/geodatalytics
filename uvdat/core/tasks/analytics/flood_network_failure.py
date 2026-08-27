from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from celery import shared_task
from django.conf import settings
from django_large_image import tilesource, utilities
import numpy as np

if TYPE_CHECKING:
    from django.contrib.gis.geos import Point

from uvdat.core.models import Layer, Network, TaskResult

from .analysis_type import AnalysisInputError, AnalysisTask, AnalysisType
from .flood_simulation import FloodSimulation


class FloodNetworkFailure(AnalysisType):
    def __init__(self):
        super().__init__()
        self.name = "Flood Network Failure"
        self.description = (
            "Select an urban network and flood simulation result "
            "to determine network failures during the flood event."
        )
        self.db_value = "flood_network_failure"
        self.input_types = {
            "network": "Network",
            "flood_simulation": "TaskResult",
            "depth_tolerance_meters": "number",
            "station_radius_meters": "number",
        }
        self.input_defaults = {
            "depth_tolerance_meters": 0.1,
            "station_radius_meters": 30,
        }
        self.output_types = {"failures": "network_animation"}
        self.attribution = "Northeastern University & Kitware, Inc."

    @classmethod
    def is_enabled(cls):
        return settings.UVDAT_ENABLE_FLOOD_NETWORK_FAILURE

    def get_input_options(self):
        return {
            "network": Network.objects.all(),
            "flood_simulation": TaskResult.objects.filter(task_type=FloodSimulation().db_value),
            "depth_tolerance_meters": [0.1, 0.5, 1, 2, 3],
            "station_radius_meters": [10, 15, 20, 25, 30, 35, 40, 45, 50],
        }

    def run_task(self, *, project, **inputs):
        result = TaskResult.objects.create(
            name="Flood Network Failure",
            task_type=self.db_value,
            inputs=inputs,
            project=project,
            status="Initializing task...",
        )
        flood_network_failure.delay(result.id)
        return result

    def validate_inputs(self, inputs):
        super().validate_inputs(inputs)
        tolerance = float(inputs.get("depth_tolerance_meters"))
        if tolerance <= 0:
            raise AnalysisInputError("Depth tolerance must be greater than 0")
        radius_meters = float(inputs.get("station_radius_meters"))
        if radius_meters < 10:
            # data is at 10 meter resolution
            raise AnalysisInputError("Station radius must be greater than 10")

    def finalize(self, result):
        pass


def _get_station_region(point: Point, radius_meters: float) -> dict[str, Any]:
    """Get a rectangular region around a point, sized by radius_meters."""
    earth_radius_meters = 6378000
    lat_delta = (radius_meters / earth_radius_meters) * (180 / math.pi)
    lon_delta = (
        (radius_meters / earth_radius_meters) * (180 / math.pi) / math.cos(point.y * math.pi / 180)
    )
    return {
        "top": point.y + lat_delta,
        "bottom": point.y - lat_delta,
        "left": point.x - lon_delta,
        "right": point.x + lon_delta,
        "units": "EPSG:4326",
    }


@shared_task(base=AnalysisTask)
def flood_network_failure(result_id):
    result = TaskResult.objects.get(id=result_id)
    network_id = result.inputs.get("network")
    network = Network.objects.get(id=network_id)
    flood_sim_id = result.inputs.get("flood_simulation")
    flood_sim = TaskResult.objects.get(id=flood_sim_id)
    tolerance = float(result.inputs.get("depth_tolerance_meters"))
    radius_meters = float(result.inputs.get("station_radius_meters"))

    # Run task
    result.name = (
        f"Failures for Network {network.id} with Flood Result {flood_sim.id}, "
        f"{tolerance} Tolerance, {radius_meters} Radius"
    )
    result.save()

    n_nodes = network.nodes.count()
    flood_dataset_id = flood_sim.outputs.get("flood")
    flood_layer = Layer.objects.get(dataset__id=flood_dataset_id)

    # Precompute node regions
    node_regions = {
        node.id: _get_station_region(node.location, radius_meters) for node in network.nodes.all()
    }

    # Assume that all frames in flood_layer refer to frames of the same RasterData
    raster = flood_layer.frames.first().raster
    raster_path = utilities.field_file_to_local_path(raster.cloud_optimized_geotiff)
    source = tilesource.get_tilesource_from_path(raster_path)
    metadata = source.getMetadata()

    animation_results = {}
    node_failures = []
    for frame in metadata.get("frames", []):
        frame_index = frame.get("Index")
        result.write_status(
            f"Evaluating flood levels at {n_nodes} nodes for frame {frame_index}..."
        )
        for node_id, node_region in node_regions.items():
            region_data, _ = source.getRegion(
                region=node_region,
                frame=frame_index,
                format="numpy",
            )
            if node_id not in node_failures and np.any(np.where(region_data > tolerance)):
                node_failures.append(node_id)
        animation_results[frame_index] = node_failures.copy()
    result.write_outputs({"failures": animation_results})
