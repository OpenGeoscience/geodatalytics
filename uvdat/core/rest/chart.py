from __future__ import annotations

from django.http import HttpResponse
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from uvdat.core.models import Chart
from uvdat.core.rest.access_control import GuardianFilter, GuardianPermission
from uvdat.core.rest.serializers import ChartSerializer, FileItemSerializer


class ChartViewSet(ModelViewSet):
    queryset = Chart.objects.all()
    serializer_class = ChartSerializer
    permission_classes = [GuardianPermission]
    filter_backends = [GuardianFilter]

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

    def validate_editable(self, chart, func, *args, **kwargs):
        if chart.editable:
            return func(*args, **kwargs)
        else:
            return HttpResponse("Not an editable chart.", status=400)

    @action(detail=True, methods=["post"])
    def new_line(self, request, **kwargs):
        chart = self.get_object()
        self.validate_editable(chart, chart.new_line)
        return HttpResponse(status=200)

    @action(detail=True, methods=["post"])
    def rename_lines(self, request, **kwargs):
        chart = self.get_object()
        self.validate_editable(chart, chart.rename_lines, new_names=request.data)
        return HttpResponse(status=200)

    @action(detail=True, methods=["post"])
    def clear(self, request, **kwargs):
        chart = self.get_object()
        self.validate_editable(chart, chart.clear)
        return HttpResponse(status=200)
