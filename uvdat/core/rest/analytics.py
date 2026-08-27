from __future__ import annotations

import inspect

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer
from rest_framework.viewsets import ReadOnlyModelViewSet

from uvdat.core.models import Project, TaskResult
import uvdat.core.rest.serializers as uvdat_serializers
from uvdat.core.tasks.analytics import analysis_types
from uvdat.core.tasks.analytics.analysis_type import AnalysisInputError

EXCLUDE_FIELDS = ["chart_data", "chart_options", "nodes", "outputs", "metadata"]


class AnalyticsViewSet(ReadOnlyModelViewSet):
    queryset = TaskResult.objects.all()
    serializer_class = uvdat_serializers.TaskResultSerializer

    @action(
        detail=False,
        methods=["get"],
        url_path=r"project/(?P<project_id>[\d*]+)/types",
    )
    def list_types(self, request, project_id: int, **kwargs):
        serialized = []
        for analysis_type in analysis_types:
            instance = analysis_type()
            if not analysis_type.is_enabled() or (
                request.user.is_anonymous
                and not TaskResult.objects.filter(
                    task_type=instance.db_value, project__allow_unauthenticated=True
                ).exists()
            ):
                continue
            filtered_input_options = {}
            for k, v in instance.get_input_options().items():
                if isinstance(v, QuerySet):
                    filtered_queryset = v.filter_by_projects(Project.objects.filter(id=project_id))
                    input_serializer = next(
                        iter(
                            [
                                s
                                for _, s in inspect.getmembers(uvdat_serializers, inspect.isclass)
                                if issubclass(s, ModelSerializer)
                                and s.Meta.model == filtered_queryset.model
                            ]
                        ),
                        None,
                    )
                    if input_serializer is not None:
                        options = [
                            {
                                k: v
                                for k, v in input_serializer(o).data.items()
                                if k not in EXCLUDE_FIELDS
                            }
                            for o in filtered_queryset
                        ]
                    else:
                        options = [{"id": o.id, "name": o.name} for o in filtered_queryset]
                elif any(not isinstance(o, dict) for o in v):
                    options = [{"id": o, "name": o} for o in v]
                else:
                    options = v
                filtered_input_options[k] = options
            serializer = uvdat_serializers.AnalysisTypeSerializer(
                data={
                    "name": instance.name,
                    "db_value": instance.db_value,
                    "description": instance.description,
                    "details": instance.details,
                    "attribution": instance.attribution,
                    "input_options": filtered_input_options,
                    "input_types": instance.input_types,
                    "input_defaults": instance.input_defaults,
                    "output_types": instance.output_types,
                }
            )
            serializer.is_valid(raise_exception=True)
            serialized.append(serializer.data)
        return Response(serialized, status=200)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"project/(?P<project_id>[\d*]+)/types/(?P<task_type>.+)/results",
    )
    def list_results(self, request, project_id: int, task_type: str, **kwargs):
        results = TaskResult.objects.filter(
            project__id=project_id,
            task_type=task_type,
        )
        return Response(
            [uvdat_serializers.TaskResultSerializer(result).data for result in results],
            status=200,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path=r"project/(?P<project_id>[\d*]+)/types/(?P<task_type>.+)/run",
    )
    def run(self, request, project_id: int, task_type: str, **kwargs):
        project = Project.objects.get(id=project_id)
        if not project.user_can_edit(request.user):
            return Response(
                "You do not have permission to run analytics tasks in this project.",
                status=403,
            )
        analysis_type_class = next(
            iter(at for at in analysis_types if at().db_value == task_type), None
        )
        if analysis_type_class is None or not analysis_type_class.is_enabled():
            return Response(f'Analysis type "{task_type}" not found', status=404)
        analysis_type = analysis_type_class()
        try:
            analysis_type.validate_inputs(request.data)
        except AnalysisInputError as e:
            return Response(str(e), status=400)
        result = analysis_type.run_task(project=project, **request.data)
        result.creator = request.user
        result.save()
        return Response(
            uvdat_serializers.TaskResultSerializer(result).data,
            status=200,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path=r"(?P<result_id>[\d*]+)/subscribe",
    )
    def subscribe(self, request, result_id, **kwargs):
        task_result = get_object_or_404(TaskResult, id=result_id)
        if task_result.completed:
            return Response("Task already completed. Subscription not applied.", status=410)
        task_result.subscribers.add(request.user)
        return Response(
            uvdat_serializers.TaskResultSerializer(task_result).data,
            status=200,
        )
