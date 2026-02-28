from __future__ import annotations

from django.core import signing
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from uvdat.core.models import Dataset, FileItem, RasterData, VectorData
from uvdat.core.rest.access_control import GuardianFilter, GuardianPermission
from uvdat.core.rest.serializers import (
    FileItemSerializer,
    RasterDataSerializer,
    VectorDataSerializer,
)


class FileItemViewSet(ModelViewSet):
    queryset = FileItem.objects.all()
    serializer_class = FileItemSerializer
    permission_classes = [GuardianPermission]
    filter_backends = [GuardianFilter]

    def get_queryset(self):
        qs = super().get_queryset()
        project_id: str | None = self.request.query_params.get("project")
        if project_id is None or not project_id.isdigit():
            return qs

        return qs.filter(project=int(project_id))

    def create(self, request, *args, **kwargs):
        file_key = request.data.get("file")
        try:
            file_key_data = signing.loads(file_key)
            file_key = file_key_data.get("object_key")
        except (signing.BadSignature, TypeError):
            return Response({"detail": "Invalid file key"}, status=400)

        dataset_id = request.data.get("dataset")
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist:
            return Response({"detail": "Dataset not found"}, status=404)

        file_item = FileItem.objects.create(
            name=request.data.get("name", "File"),
            file_type=request.data.get("file_type", "json"),
            metadata=request.data.get("metadata", {}),
            index=request.data.get("index", 0),
            dataset=dataset,
            file=file_key,
        )
        serializer = self.get_serializer(file_item)
        return Response(serializer.data, status=201)

    @action(detail=True, methods=["get"])
    def data(self, request, **kwargs):
        file_item: FileItem = self.get_object()

        data = [
            RasterDataSerializer(raster).data
            for raster in RasterData.objects.filter(source_file=file_item)
        ]
        data.extend(
            VectorDataSerializer(vector).data
            for vector in VectorData.objects.filter(source_file=file_item)
        )
        return Response(data, status=200)
