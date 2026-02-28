from __future__ import annotations

import typing
from typing import Any

from django.contrib.auth.models import User
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from uvdat.core.models import Project
from uvdat.core.rest.access_control import GuardianFilter, GuardianPermission
from uvdat.core.rest.serializers import ProjectPermissionsSerializer, ProjectSerializer

if typing.TYPE_CHECKING:
    from rest_framework.request import Request


class ProjectViewSet(ModelViewSet):
    queryset = Project.objects.all().order_by("name")
    serializer_class = ProjectSerializer
    permission_classes = [GuardianPermission]
    filter_backends = [GuardianFilter]

    def perform_create(self, serializer):
        project: Project = serializer.save()
        user: User = self.request.user
        project.set_permissions(owner=user)

    @swagger_auto_schema(method="PUT", request_body=ProjectPermissionsSerializer)
    @action(detail=True, methods=["PUT"])
    def permissions(self, request: Request, *args: Any, **kwargs: Any):
        if request.user.is_anonymous:
            raise RuntimeError("Anonymous user received after guardian filter")
        user = typing.cast("User", request.user)

        # Only the owner can modify project permissions
        project: Project = self.get_object()
        if not user.has_perm("owner", project):
            return Response(status=403)

        serializer = ProjectPermissionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        project.set_permissions(
            owner=User.objects.get(id=data["owner_id"]),
            collaborator=list(User.objects.filter(id__in=data["collaborator_ids"])),
            follower=list(User.objects.filter(id__in=data["follower_ids"])),
        )

        return Response(ProjectSerializer(project).data, status=200)
