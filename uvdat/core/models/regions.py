from __future__ import annotations

from django.contrib.gis.db import models as geo_models
from django.db import models

from .data import VectorFeature
from .dataset import Dataset
from .project import Project
from .querysets import ProjectQuerySet


class Region(models.Model):
    name = models.CharField(max_length=255)
    vector_feature = models.ForeignKey(
        VectorFeature, on_delete=models.CASCADE, related_name="regions", null=True
    )
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="regions", null=True
    )
    dataset = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="regions", null=True
    )
    metadata = models.JSONField(blank=True, null=True)
    boundary = geo_models.MultiPolygonField()

    project_filter_path = "project|dataset__project"
    objects = ProjectQuerySet.as_manager()

    class Meta:
        constraints = [
            # We enforce name uniqueness across datasets and projects
            models.UniqueConstraint(
                name="unique-region-name", fields=["project", "dataset", "name"]
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(dataset__isnull=False, project__isnull=True)
                    | models.Q(dataset__isnull=True, project__isnull=False)
                ),
                name="dataset_or_project_constraint",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.id})"
