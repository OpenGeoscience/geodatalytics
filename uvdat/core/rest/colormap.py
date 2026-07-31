from __future__ import annotations

from django.db import transaction
import jsonschema
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from uvdat.core.models import Colormap, Project
from uvdat.core.rest.serializers import ColormapSerializer


class ColormapViewSet(ModelViewSet):
    queryset = Colormap.objects.all()
    serializer_class = ColormapSerializer

    def create(self, request, **kwargs):
        project = Project.objects.get(id=request.data.get("project"))
        if not (
            request.user.is_superuser
            or project.owner == request.user
            or request.user in project.collaborators()
        ):
            return Response(
                "You do not have permission to create colormaps in this project.",
                status=400,
            )
        serializer = ColormapSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            try:
                serializer.save()
            except jsonschema.exceptions.ValidationError as e:
                return Response(e.message, status=400)
        return Response(serializer.data, status=200)
