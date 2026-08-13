from __future__ import annotations

from typing import TYPE_CHECKING, Self

from django.db import models

if TYPE_CHECKING:
    from .project import Project


class ProjectQuerySet(models.QuerySet):
    """
    `QuerySet` that filters by project membership.

    Models using this queryset (via `as_manager()`) must define a `project_filter_path` class
    attribute:

    * A lookup string (e.g. `"project"`, `"dataset__project"`) that resolves to the Project FK/M2M
      from the model.
    * `None` to skip filtering (`filter_by_projects` returns the full queryset).

    Models may also set `project_filter_allow_null = True` to include rows where the
    `project_filter_path` leads to a NULL FK (i.e. not associated with any Project). By default,
    only rows that have an associated Project are returned.
    """

    def filter_by_projects(self, projects: models.QuerySet[Project]) -> Self:
        """Return rows visible to users who have access to *projects*."""
        path: str | None = self.model.project_filter_path
        allow_null: bool = getattr(self.model, "project_filter_allow_null", False)

        if path is None:
            return self.all()

        query = models.Q(**{f"{path}__in": projects})
        if allow_null:
            query |= models.Q(**{f"{path}__isnull": True})
        return self.filter(query).distinct()
