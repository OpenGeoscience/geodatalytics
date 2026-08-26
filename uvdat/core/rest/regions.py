from __future__ import annotations

from django.contrib.gis.geos import MultiPolygon, Polygon
from rest_framework.viewsets import ModelViewSet

from uvdat.core.models import Project, Region

from .serializers import RegionSerializer


class RegionViewSet(ModelViewSet):
    queryset = Region.objects.all()
    serializer_class = RegionSerializer

    def perform_create(self, serializer):
        coords = self.request.data.get("boundary")
        project_id = self.request.data.get("project_id")
        serializer.save(
            project=Project.objects.get(id=project_id),
            boundary=MultiPolygon(*[Polygon(*poly) for poly in coords]),
        )
