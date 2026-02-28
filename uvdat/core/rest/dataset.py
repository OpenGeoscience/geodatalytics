from __future__ import annotations

from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from uvdat.core.models import Dataset, DatasetTag
from uvdat.core.rest.access_control import DatasetGuardianPermission, GuardianFilter
from uvdat.core.rest.serializers import (
    DatasetSerializer,
    FileItemSerializer,
    LayerSerializer,
    NetworkSerializer,
    RasterDataSerializer,
    TaskResultSerializer,
    VectorDataSerializer,
)


class DatasetViewSet(ModelViewSet):
    queryset = Dataset.objects.all()
    serializer_class = DatasetSerializer
    permission_classes = [DatasetGuardianPermission]
    filter_backends = [GuardianFilter]

    def get_queryset(self):
        qs = super().get_queryset()
        project_id: str | None = self.request.query_params.get("project")
        if project_id is None or not project_id.isdigit():
            return qs

        return qs.filter(project=int(project_id))

    def perform_create(self, serializer):
        # Set the owner of the object to the current user
        instance = serializer.save()
        instance.set_owner(self.request.user)

    @action(detail=False, methods=["get"])
    def tags(self, request, **kwargs):
        data = [t.tag for t in DatasetTag.objects.all()]
        return Response(data, status=200)

    @action(detail=True, methods=["get"])
    def layers(self, request, **kwargs):
        dataset: Dataset = self.get_object()
        layers = list(dataset.layers.all())
        serializer = LayerSerializer(layers, many=True)
        return Response(serializer.data, status=200)

    @action(detail=True, methods=["get"])
    def data(self, request, **kwargs):
        dataset: Dataset = self.get_object()

        data = [RasterDataSerializer(raster).data for raster in dataset.rasters.all()]
        data.extend(VectorDataSerializer(vector).data for vector in dataset.vectors.all())
        return Response(data, status=200)

    @action(detail=True, methods=["get"])
    def networks(self, request, **kwargs):
        dataset = self.get_object()
        return Response(
            [NetworkSerializer(network).data for network in dataset.get_networks().all()],
            status=200,
        )

    @action(detail=True, methods=["get"])
    def files(self, request, **kwargs):
        dataset = self.get_object()
        return Response(
            [FileItemSerializer(file).data for file in dataset.source_files.all()],
            status=200,
        )

    @action(detail=True, methods=["post"])
    def convert(self, request, **kwargs):
        dataset = self.get_object()
        result = dataset.spawn_conversion_task(
            layer_options=request.data.get("layer_options"),
            network_options=request.data.get("network_options"),
            region_options=request.data.get("region_options"),
        )

        return Response(TaskResultSerializer(result).data, status=200)
