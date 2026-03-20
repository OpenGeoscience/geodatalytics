from __future__ import annotations

import json
from pathlib import Path
import tempfile

from django.contrib.gis.db import models as geomodels
from django.core.files.base import ContentFile
from django.db import models
from django.dispatch import receiver
import large_image
from s3_file_field import S3FileField

from .dataset import Dataset
from .file_item import FileItem
from .querysets import ProjectQuerySet


class RasterData(models.Model):
    name = models.CharField(max_length=255, default="Raster Data")
    dataset = models.ForeignKey(Dataset, related_name="rasters", on_delete=models.CASCADE)
    source_file = models.ForeignKey(FileItem, null=True, on_delete=models.CASCADE)
    cloud_optimized_geotiff = S3FileField(null=True)
    metadata = models.JSONField(blank=True, null=True)

    project_filter_path = "dataset__project"
    objects = ProjectQuerySet.as_manager()

    def __str__(self):
        return f"{self.name} ({self.id})"

    def get_image_data(self, resolution: float = 1.0):
        with tempfile.TemporaryDirectory() as tmp:
            raster_path = Path(tmp, "raster")
            with raster_path.open("wb") as raster_file:
                raster_file.write(self.cloud_optimized_geotiff.read())
            source = large_image.open(raster_path)
            data, _data_format = source.getRegion(format="numpy")
            data = data[:, :, 0]
            if resolution != 1.0:
                step = int(1 / resolution)
                data = data[::step][::step]
            return data.tolist()


class VectorData(models.Model):
    name = models.CharField(max_length=255, default="Vector Data")
    dataset = models.ForeignKey(Dataset, related_name="vectors", on_delete=models.CASCADE)
    source_file = models.ForeignKey(FileItem, null=True, on_delete=models.CASCADE)
    geojson_data = S3FileField(null=True)
    summary = models.JSONField(blank=True, null=True)
    metadata = models.JSONField(blank=True, null=True)

    project_filter_path = "dataset__project"
    objects = ProjectQuerySet.as_manager()

    def __str__(self):
        return f"{self.name} ({self.id})"

    def write_geojson_data(self, content: str | dict):
        if isinstance(content, str):
            data = content
        elif isinstance(content, dict):
            data = json.dumps(content)
        else:
            raise TypeError(f"Invalid content type supplied: {type(content)}")

        self.geojson_data.save("vectordata.geojson", ContentFile(data.encode()))

    def read_geojson_data(self) -> dict:
        """Read and load the data from geojson_data into a dict."""
        with self.geojson_data.open() as f:
            return json.load(f)

    def get_summary(self, *, cache=True):  # noqa: C901
        self.check_color_props_coverage()
        if cache and self.summary:
            return self.summary
        # Limit number of unique values to return for non-numeric fields
        value_set_max_length = 1000
        summary = {"feature_types": [], "properties": {}}
        exclude_keys = ["node_id", "edge_id", "to_node_id", "from_node_id", "fill", "stroke"]
        # Create sets of all values for all properties (except excluded)
        # and a list of the feature types that exist (point, line, polygon)
        for feature in self.features.all():
            feature_type = feature.geometry.geom_type
            if feature_type not in summary["feature_types"]:
                summary["feature_types"].append(feature_type)
            for k, v in feature.properties.items():
                if k not in exclude_keys and v is not None and v != "":
                    if k not in summary["properties"]:
                        summary["properties"][k] = {"value_set": set(), "count": 0}
                    new_val = v if isinstance(v, list) else [v]
                    for item in new_val:
                        summary["properties"][k]["value_set"].add(item)
                        summary["properties"][k]["count"] += 1
        # Once sets are complete, reevaluate each set and create a `sample_label` for each property
        for k in summary["properties"]:
            types = {type(v).__name__ for v in summary["properties"][k]["value_set"]}
            summary["properties"][k]["types"] = list(types)
            # If a property has only numeric values, return the range instead of a set of values
            if len(types.intersection({"int", "float"})) == len(types):
                value_range = [
                    min(summary["properties"][k]["value_set"]),
                    max(summary["properties"][k]["value_set"]),
                ]
                if value_range[0] < value_range[1]:
                    del summary["properties"][k]["value_set"]
                    summary["properties"][k]["range"] = value_range
                    summary["properties"][k]["sample_label"] = (
                        f"[{value_range[0]}, {value_range[1]}]"
                    )
            # Otherwise, limit the value set to the maximum length
            if summary["properties"][k].get("range") is None:
                summary["properties"][k]["value_set"] = list(summary["properties"][k]["value_set"])[
                    :value_set_max_length
                ]
                summary["properties"][k]["sample_label"] = ", ".join(
                    str(v) for v in summary["properties"][k]["value_set"][:3]
                )
                if len(summary["properties"][k]["value_set"]) > 3:
                    summary["properties"][k]["sample_label"] += "..."
        self.summary = summary
        self.save()
        return summary

    def check_color_props_coverage(self):
        if self.summary is not None and self.summary.get("color_props_coverage") is None:
            n_covered_features = self.features.filter(
                properties__has_keys=["fill", "stroke"]
            ).count()
            coverage = n_covered_features / self.features.count()
            self.summary["color_props_coverage"] = (
                "none" if coverage == 0 else "full" if coverage == 1 else "partial"
            )
            self.save()


class VectorFeature(models.Model):
    vector_data = models.ForeignKey(
        VectorData, on_delete=models.CASCADE, related_name="features", null=True
    )
    geometry = geomodels.GeometryField()
    properties = models.JSONField()

    def __str__(self):
        return f"VectorFeature ({self.id})"

    @property
    def dataset(self):
        return self.vector_data.dataset


@receiver(models.signals.post_delete, sender=RasterData)
def delete_raster_content(sender, instance, **kwargs):
    if instance.cloud_optimized_geotiff:
        instance.cloud_optimized_geotiff.delete(save=False)


@receiver(models.signals.post_delete, sender=VectorData)
def delete_vector_content(sender, instance, **kwargs):
    if instance.geojson_data:
        instance.geojson_data.delete(save=False)
