from __future__ import annotations

from django.db import transaction
import jsonschema
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from uvdat.core.models import Layer, LayerFrame, LayerStyle, Project
from uvdat.core.rest.querysets import layer_queryset_with_previews
from uvdat.core.rest.serializers import (
    LayerFrameSerializer,
    LayerSerializer,
    LayerStyleWithPreviewsSerializer,
)


class LayerViewSet(ReadOnlyModelViewSet):
    serializer_class = LayerSerializer

    def get_queryset(self):
        return layer_queryset_with_previews()

    @action(detail=True, methods=["get"])
    def frames(self, request, **kwargs):
        layer: Layer = self.get_object()
        frames = list(layer.frames.all())
        serializer = LayerFrameSerializer(frames, many=True)
        return Response(serializer.data, status=200)


class LayerFrameViewSet(ReadOnlyModelViewSet):
    queryset = LayerFrame.objects.all()
    serializer_class = LayerFrameSerializer


class LayerStyleViewSet(ModelViewSet):
    queryset = LayerStyle.objects.all()
    serializer_class = LayerStyleWithPreviewsSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        project_id = int(self.request.query_params.get("project", -1))
        if project_id > -1:
            qs = qs.filter(project=int(project_id))
        layer_id = int(self.request.query_params.get("layer", -1))
        if layer_id > -1:
            qs = qs.filter(layer=int(layer_id))
        return layer_queryset_with_previews(qs, for_layer_style=True)

    def create(self, request, **kwargs):
        project = Project.objects.get(id=request.data.get("project"))
        if not project.user_can_edit(request.user):
            return Response(
                "You do not have permission to create styles in this project.",
                status=403,
            )
        is_default = request.data.pop("is_default", False)
        serializer = LayerStyleWithPreviewsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            try:
                instance = serializer.save()
            except jsonschema.exceptions.ValidationError as e:
                return Response(e.message, status=400)
            if is_default and instance.layer.default_style != instance:
                instance.layer.default_style = instance
                instance.layer.save()
        return Response(serializer.data, status=200)

    def partial_update(self, request, **kwargs):
        instance = self.get_object()
        is_default = request.data.pop("is_default", False)
        serializer = LayerStyleWithPreviewsSerializer(
            instance, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            try:
                serializer.save()
            except jsonschema.exceptions.ValidationError as e:
                return Response(e.message, status=400)
            if is_default and instance.layer.default_style != instance:
                instance.layer.default_style = instance
                instance.layer.save()
        return Response(serializer.data, status=200)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        with transaction.atomic():
            if instance.layer.default_style == instance:
                instance.layer.default_style = (
                    LayerStyle.objects.filter(layer=instance.layer).exclude(id=instance.id).first()
                )
                instance.layer.save()
            self.perform_destroy(instance)
        return Response(status=204)
