from __future__ import annotations

from abc import ABC, abstractmethod

import celery

from uvdat.core.models import TaskResult


class AnalysisType(ABC):
    def __init__(self, *args):
        self.name = ""
        self.description = ""
        self.details = None
        self.db_value = ""  # cannot be longer than 25 characters
        self.input_types = {}
        self.input_defaults = {}
        self.output_types = {}
        self.attribution = "Kitware, Inc."

    @classmethod
    @abstractmethod
    def is_enabled(cls):
        raise NotImplementedError

    @abstractmethod
    def get_input_options(self):
        raise NotImplementedError

    @abstractmethod
    def run_task(self, *, project, **inputs):
        raise NotImplementedError

    def validate_inputs(self, inputs):
        for input_name in self.input_types:
            if input_name not in inputs:
                raise AnalysisInputError(f"{input_name} not provided.")

    @abstractmethod
    def finalize(self, result):
        raise NotImplementedError


class AnalysisInputError(Exception):
    pass


class AnalysisTask(celery.Task):
    def get_task_result(self, args):
        # All analysis tasks use this signature
        task_result_id = args[0]
        return TaskResult.objects.get(pk=task_result_id)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        task_result = self.get_task_result(args)
        err_msg = (
            str(exc)
            if isinstance(exc, AnalysisInputError)
            else "An error occurred during this task. See logs for details."
        )
        task_result.write_error(err_msg)

    def after_return(self, status, retval, task_id, args, kwargs, einfo):  # noqa: PLR0913
        # Avoid circular import
        from . import analysis_types  # noqa: PLC0415

        task_result = self.get_task_result(args)
        task_result.complete()

        analysis_type = next(
            iter(t for t in analysis_types if t().db_value == task_result.task_type), None
        )
        if analysis_type is not None:
            analysis_type().finalize(task_result)
