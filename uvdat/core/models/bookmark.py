from __future__ import annotations

from django.contrib.gis.db import models as geo_models
from django.db import models
from s3_file_field import S3FileField

from .basemap import Basemap
from .chart import Chart
from .layer import Layer
from .networks import Network
from .project import Project
from .querysets import ProjectQuerySet
from .task_result import TaskResult


class Bookmark(models.Model):
    name = models.CharField(max_length=255)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="views", null=True)
    thumbnail = S3FileField()

    theme = models.CharField(max_length=10, default="light")
    current_analysis_type = models.CharField(
        max_length=25,
        blank=True,  # max length matches TaskResult.task_type
    )
    current_result = models.ForeignKey(
        TaskResult, on_delete=models.CASCADE, related_name="views", null=True
    )
    current_basemap = models.ForeignKey(
        Basemap, on_delete=models.CASCADE, related_name="views", null=True
    )
    current_chart = models.ForeignKey(
        Chart, on_delete=models.CASCADE, related_name="views", null=True
    )
    current_network = models.ForeignKey(
        Network, on_delete=models.CASCADE, related_name="views", null=True
    )
    left_sidebar_open = models.BooleanField(default=False)
    right_sidebar_open = models.BooleanField(default=False)
    map_zoom = models.IntegerField(null=True)
    map_center = geo_models.PointField(null=True)
    panel_arrangement = models.JSONField(blank=True, null=True)
    selected_layers = models.ManyToManyField(Layer, related_name="views", blank=True)
    selected_layer_current_frames = models.JSONField(blank=True, null=True)
    selected_layer_order = models.JSONField(blank=True, null=True)
    selected_layer_styles = models.JSONField(blank=True, null=True)

    project_filter_path = "project"
    objects = ProjectQuerySet.as_manager()

    class Meta:
        constraints = [
            # We enforce name uniqueness across projects
            models.UniqueConstraint(name="uniqueviewname", fields=["project", "name"])
        ]

    def __str__(self):
        return f"{self.name} ({self.id})"
