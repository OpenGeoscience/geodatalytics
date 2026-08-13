from __future__ import annotations

from guardian.shortcuts import get_objects_for_user
from rest_framework.exceptions import ValidationError
from rest_framework.filters import BaseFilterBackend
from rest_framework.permissions import SAFE_METHODS, BasePermission

from uvdat.core.models.dataset import Dataset
from uvdat.core.models.project import Project


class GuardianPermission(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_anonymous:
            return request.method == "GET"
        return super().has_permission(request, view)

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

        permitted_projects = Project.objects.all()
        if request.user.is_anonymous:
            permitted_projects = permitted_projects.filter(allow_unauthenticated=True)
        elif not request.user.is_superuser:
            permitted_projects = get_objects_for_user(
                klass=permitted_projects,
                user=request.user,
                perms=perms,
                any_perm=True,
            )

        # If the object remains in the queryset after this function filters it, then the user has
        # the required permission on at least one associated project
        return queryset.filter_by_projects(permitted_projects).exists()


class DatasetGuardianPermission(GuardianPermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True

        if request.user.is_anonymous:
            return (
                request.method == "GET"
                and obj.project_set.filter(allow_unauthenticated=True).exists()
            )

        # Prohibit delete and patch requests unless user is owner
        return request.method not in ["DELETE", "PATCH"] or obj.owner() == request.user


class GuardianFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        if not hasattr(queryset, "filter_by_projects"):
            raise NotImplementedError

        permitted_projects = Project.objects.all()

        project_id = request.query_params.get("project")
        if project_id:
            if not project_id.isdigit():
                raise ValidationError({"project": "Must be a valid project ID."})
            permitted_projects = permitted_projects.filter(id=project_id)

        if request.user.is_anonymous:
            permitted_projects = permitted_projects.filter(allow_unauthenticated=True)
            if queryset.model == Dataset:
                # special case for datasets when not authenticated;
                # unauthenticated users can only see datasets added to projects they can see
                return queryset.filter(project__in=permitted_projects)
        elif not request.user.is_superuser:
            permitted_projects = get_objects_for_user(
                klass=permitted_projects,
                user=request.user,
                perms=["follower", "collaborator", "owner"],
                any_perm=True,
            ) | permitted_projects.filter(allow_unauthenticated=True)

        # Return queryset filtered by objects that are within these projects
        return queryset.filter_by_projects(permitted_projects)
