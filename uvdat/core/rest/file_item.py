from __future__ import annotations

from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from uvdat.core.models import FileItem, RasterData, VectorData
from uvdat.core.rest.serializers import (
    FileItemSerializer,
    RasterDataSerializer,
    VectorDataSerializer,
)


class FileItemViewSet(ModelViewSet):
    queryset = FileItem.objects.all()
    serializer_class = FileItemSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        project_id: str | None = self.request.query_params.get("project")
        if project_id is None or not project_id.isdigit():
            return qs

        return qs.filter(project=int(project_id))

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
