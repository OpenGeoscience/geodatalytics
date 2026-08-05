from __future__ import annotations

from django.db import transaction
import jsonschema
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from uvdat.core.models import Project, ViewState
from uvdat.core.rest.serializers import ViewStateSerializer


class ViewStateViewSet(ModelViewSet):
    queryset = ViewState.objects.all()
    serializer_class = ViewStateSerializer

    def create(self, request, **kwargs):
        project = Project.objects.get(id=request.data.get("project"))
        if not project.user_can_edit(request.user):
            return Response(
                "You do not have permission to create view states in this project.",
                status=403,
            )
        serializer = ViewStateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            try:
                serializer.save()
            except jsonschema.exceptions.ValidationError as e:
                return Response(e.message, status=400)
        return Response(serializer.data, status=200)
