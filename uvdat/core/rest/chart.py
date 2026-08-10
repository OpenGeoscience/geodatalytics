from __future__ import annotations

import json

from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from uvdat.core.models import Chart
from uvdat.core.rest.serializers import ChartSerializer, FileItemSerializer, TaskResultSerializer


class ChartViewSet(ModelViewSet):
    queryset = Chart.objects.all()
    serializer_class = ChartSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        project_id: str | None = self.request.query_params.get("project")
        if project_id is None or not project_id.isdigit():
            return qs

        return qs.filter(project=int(project_id))

    @action(detail=True, methods=["get"])
    def files(self, request, **kwargs):
        chart = self.get_object()
        return Response(
            [FileItemSerializer(file).data for file in chart.fileitem_set.all()],
            status=200,
        )

    @action(detail=True, methods=["post"])
    def convert(self, request, **kwargs):
        chart = self.get_object()
        conversion_options = request.data.get("conversion_options")
        if conversion_options is None:
            return Response("Missing required conversion_options.", status=400)
        result = chart.spawn_conversion_task(conversion_options=json.loads(conversion_options))
        result.creator = request.user
        result.save()

        return Response(TaskResultSerializer(result).data, status=200)
