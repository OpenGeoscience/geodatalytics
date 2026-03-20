from __future__ import annotations

from guardian.shortcuts import get_objects_for_user
from rest_framework.filters import BaseFilterBackend
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated

from uvdat.core import models
from uvdat.core.models.project import Project


class GuardianPermission(IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True

        perms = ["follower", "collaborator", "owner"]
        if request.method not in SAFE_METHODS:
            perms = ["collaborator", "owner"]
        if request.method == "DELETE":
            perms = ["owner"]

        # Create queryset out of single object, so it can be passed to the filter method
        queryset = type(obj).objects.filter(pk=obj.pk)
        if not hasattr(queryset, "filter_by_projects"):
            raise NotImplementedError

        # Get all projects user has access to
        user_projects = get_objects_for_user(
            klass=models.Project, user=request.user, perms=perms, any_perm=True
        )

        # If the object remains in the queryset after this function filters it, then the user has
        # the required permission on at least one associated project
        return queryset.filter_by_projects(user_projects).exists()


class DatasetGuardianPermission(GuardianPermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True

        # Prohibit delete and patch requests unless user is owner
        return request.method not in ["DELETE", "PATCH"] or obj.owner() == request.user


class GuardianFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        if not hasattr(queryset, "filter_by_projects"):
            raise NotImplementedError

        project_id = request.query_params.get("project")
        if project_id:
            # Return queryset filtered by objects that are within these projects
            return queryset.filter_by_projects(Project.objects.filter(id=project_id))

        if request.user.is_superuser:
            return queryset

        user_projects = get_objects_for_user(
            klass=models.Project,
            user=request.user,
            perms=["follower", "collaborator", "owner"],
            any_perm=True,
        )

        # Return queryset filtered by objects that are within these projects
        return queryset.filter_by_projects(user_projects)
