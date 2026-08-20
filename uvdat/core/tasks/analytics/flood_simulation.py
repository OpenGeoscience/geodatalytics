from __future__ import annotations

import datetime
from pathlib import Path
import tempfile

from celery import shared_task
from django.conf import settings
from django.core.files import File

from uvdat.core.models import Chart, Colormap, Dataset, FileItem, LayerStyle, TaskResult

from .analysis_type import AnalysisTask, AnalysisType


class FloodSimulation(AnalysisType):
    def __init__(self):
        super().__init__()
        self.name = "AI Flood Simulation"
        self.description = "Select parameters to simulate a 24-hour flood of the Charles River"
        self.details = (
            "The AI extreme precipitation downscaler achieves a Mean Absolute Error (MAE) "
            "of 3.82 mm and a MAE of Annual Precipitation Maxima of 20.46 mm when tested "
            "on an unseen validation period of n=7305 days. The AI-optimized SIMHYD "
            "hydrological model achieves a Nash-Sutcliffe Efficiency (NSE) of 0.70 when "
            "tested on an unseen validation period of n=6209 days."
        )
        self.db_value = "flood_simulation"
        self.input_types = {
            "initial_conditions_id": "string",
            "time_period": "string",
            "hydrograph": "Chart",
            "potential_evapotranspiration_percentile": "number",
            "soil_moisture_percentile": "number",
            "ground_water_percentile": "number",
            "annual_probability": "number",
        }
        self.output_types = {
            "flood": "Dataset",
            "precipitation_level_mm": "number",
            "discharge_ft3_per_second": "number",
        }
        self.attribution = "Northeastern University"

    @classmethod
    def is_enabled(cls):
        return settings.UVDAT_ENABLE_FLOOD_SIMULATION

    def get_input_options(self):
        return {
            "initial_conditions_id": ["001", "002", "003"],
            "time_period": ["2031-2050", "2041-2060"],
            "hydrograph": Chart.objects.filter(name__icontains="hydrograph"),
            "potential_evapotranspiration_percentile": [{"min": 0, "max": 100, "step": 1}],
            "soil_moisture_percentile": [{"min": 0, "max": 100, "step": 1}],
            "ground_water_percentile": [{"min": 0, "max": 100, "step": 1}],
            "annual_probability": [{"min": 0, "max": 1, "step": 0.01}],
        }

    def run_task(self, *, project, **inputs):
        result = TaskResult.objects.create(
            name="Flood Simulation",
            task_type=self.db_value,
            inputs=inputs,
            project=project,
            status="Initializing task...",
        )
        flood_simulation.delay(result.id)
        return result

    def finalize(self, result):
        seconds = (result.completed - result.created).total_seconds()
        result.status = (
            f"AI Simulation completed in {seconds:.2f} seconds "
            "(compare to baseline 5-hour numerical simulation)."
        )
        result.save()


@shared_task(base=AnalysisTask)
def flood_simulation(result_id):
    # Only available with [tasks] extra
    from uvdat_flood_sim import run_sim, write_multiframe_geotiff  # noqa: PLC0415

    result = TaskResult.objects.get(id=result_id)
    result.write_status("Interpreting input values")
    initial_conditions_id = result.inputs.get("initial_conditions_id")
    time_period = result.inputs.get("time_period")
    hydrograph_id = result.inputs.get("hydrograph")
    hydrograph_chart = Chart.objects.get(id=hydrograph_id)
    hydrograph = hydrograph_chart.chart_data.get("datasets")[0].get("data")
    pet_percentile = result.inputs.get("potential_evapotranspiration_percentile")
    sm_percentile = result.inputs.get("soil_moisture_percentile")
    gw_percentile = result.inputs.get("ground_water_percentile")
    annual_probability = result.inputs.get("annual_probability")

    name = (
        f"{time_period} {annual_probability} Flood Simulation "
        f"with {hydrograph_chart.name}, initial condition set {initial_conditions_id}, "
        f"and percentiles {pet_percentile}, {sm_percentile}, {gw_percentile}"
    )
    result.name = name
    result.write_status("Running flood simulation module with specified inputs")

    outputs = run_sim(
        initial_conditions_id=initial_conditions_id,
        time_period=time_period,
        annual_probability=annual_probability,
        hydrograph=hydrograph,
        pet_percentile=pet_percentile,
        sm_percentile=sm_percentile,
        gw_percentile=gw_percentile,
        return_dict=True,
    )
    flood_results = outputs.get("flood")
    precip = outputs.get("precipitation_level_mm")
    discharge = outputs.get("discharge_ft3_per_second")

    result.write_status("Saving result to database")

    with tempfile.TemporaryDirectory() as output_folder:
        output_path = Path(output_folder) / "flood_simulation.tif"

        write_multiframe_geotiff(
            flood_results=flood_results,
            output_path=output_path,
            writer="large_image",
        )

        metadata = {
            "attribution": "Simulation code by August Posch at Northeastern University",
            "simulation_steps": [
                "downscaling_prediction",
                "hydrological_prediction",
                "hydrodynamic_prediction",
            ],
            "module_repository": "https://github.com/OpenGeoscience/uvdat-flood-sim",
            "inputs": {
                "initial_conditions_id": initial_conditions_id,
                "time_period": time_period,
                "hydrograph": hydrograph,
                "pet_percentile": pet_percentile,
                "sm_percentile": sm_percentile,
                "gw_percentile": gw_percentile,
                "annual_probability": annual_probability,
            },
            "uploaded": datetime.datetime.now(datetime.UTC).isoformat(),
        }
        name_match = Dataset.objects.filter(name__icontains=name)
        if name_match.count() > 0:
            name += f" ({name_match.count() + 1})"
        dataset = Dataset.objects.create(
            name=name,
            description="Generated by Flood Simulation Analytics Task",
            category="flood",
            metadata=metadata,
        )
        dataset.set_tags(["analytics", "flood", "simulation"])
        dataset.set_owner(result.creator)
        file_item = FileItem.objects.create(
            name=output_path.name,
            dataset=dataset,
            file_type="tif",
            file_size=output_path.stat().st_size,
            metadata=metadata,
        )
        with output_path.open("rb") as f:
            file_item.file.save(output_path.name, File(f))
        dataset.spawn_conversion_task(
            layer_options=[
                {
                    "name": "Flood Simulation",
                    "source_files": [output_path.name],
                    "frame_property": "frame",
                },
            ],
            network_options=None,
            region_options=None,
            asynchronous=False,
        )

        # Create a default style for new layer
        layer = dataset.layers.first()
        style = LayerStyle.objects.create(
            name="Flood Depth",
            layer=layer,
            project=result.project,
        )
        layer.default_style = style
        layer.save()
        cmap, _ = Colormap.objects.get_or_create(
            name="flood",
            project=result.project,
            markers=[{"color": "#002081", "value": 0}, {"color": "#2AD3FF", "value": 1}],
        )
        style.save_style_configs(
            {
                "default_frame": 0,
                "opacity": 1,
                "colors": [
                    {
                        "name": "all",
                        "visible": True,
                        "colormap": {
                            "id": cmap.id,
                            "discrete": False,
                            "clamp": True,
                            "color_by": "value",
                            "null_color": "transparent",
                            "range": [0, 2],
                        },
                    }
                ],
                "sizes": [
                    {
                        "name": "all",
                        "zoom_scaling": True,
                        "single_size": 5,
                    }
                ],
            }
        )

        result.project.datasets.add(dataset)
        result.write_outputs(
            {
                "flood": dataset.id,
                "precipitation_level_mm": precip,
                "discharge_ft3_per_second": discharge,
            }
        )
