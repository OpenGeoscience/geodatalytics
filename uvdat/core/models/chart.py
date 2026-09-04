from __future__ import annotations

from django.db import models

from uvdat.core.models.task_result import suppress_task_notifications

from .project import Project
from .querysets import ProjectQuerySet


class Chart(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, default="")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="charts", null=True)
    metadata = models.JSONField(blank=True, null=True)
    chart_data = models.JSONField(blank=True, null=True)
    chart_options = models.JSONField(blank=True, null=True)
    editable = models.BooleanField(default=False)

    project_filter_path = "project"
    objects = ProjectQuerySet.as_manager()

    def __str__(self):
        return f"{self.name} ({self.id})"

    def spawn_conversion_task(
        self,
        *,
        conversion_options=None,
        asynchronous=True,
    ):
        # Prevent circular import
        from uvdat.core.tasks.chart import convert_chart  # noqa: PLC0415

        convert_chart_signature = convert_chart.s(self.id, conversion_options)
        if asynchronous:
            # Prevent circular import
            from uvdat.core.models.task_result import TaskResult  # noqa: PLC0415

            result = TaskResult.objects.create(
                name=f"Conversion of Chart {self.name}",
                task_type="conversion",
                inputs={
                    "chart_id": self.id,
                    "conversion_options": conversion_options,
                },
                status="Initializing task...",
            )
            convert_chart_signature.delay(result_id=result.id)
            return result
        else:
            with suppress_task_notifications():
                convert_chart_signature.apply()
            return None
