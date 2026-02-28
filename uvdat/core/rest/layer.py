from __future__ import annotations

from django.db import transaction
import jsonschema
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from uvdat.core.models import Layer, LayerFrame, LayerStyle
from uvdat.core.rest.access_control import GuardianFilter, GuardianPermission
from uvdat.core.rest.serializers import (
    LayerFrameSerializer,
    LayerSerializer,
    LayerStyleSerializer,
)


class LayerViewSet(ReadOnlyModelViewSet):
    queryset = Layer.objects.select_related("dataset").all()
    serializer_class = LayerSerializer
    permission_classes = [GuardianPermission]
    filter_backends = [GuardianFilter]

    @action(detail=True, methods=["get"])
    def frames(self, request, **kwargs):
        layer: Layer = self.get_object()
        frames = list(layer.frames.all())
        serializer = LayerFrameSerializer(frames, many=True)
        return Response(serializer.data, status=200)


class LayerFrameViewSet(ReadOnlyModelViewSet):
    queryset = LayerFrame.objects.all()
    serializer_class = LayerFrameSerializer
    permission_classes = [GuardianPermission]
    filter_backends = [GuardianFilter]


class LayerStyleViewSet(ModelViewSet):
    queryset = LayerStyle.objects.all()
    serializer_class = LayerStyleSerializer
    permission_classes = [GuardianPermission]
    filter_backends = [GuardianFilter]

    def get_queryset(self):
        qs = super().get_queryset()
        project_id = int(self.request.query_params.get("project", -1))
        if project_id > -1:
            qs = qs.filter(project=int(project_id))
        layer_id = int(self.request.query_params.get("layer", -1))
        if layer_id > -1:
            qs = qs.filter(layer=int(layer_id))
        return qs

    def create(self, request, **kwargs):
        is_default = request.data.pop("is_default", False)
        serializer = LayerStyleSerializer(data=request.data)
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
        serializer = LayerStyleSerializer(instance, data=request.data, partial=True)
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
