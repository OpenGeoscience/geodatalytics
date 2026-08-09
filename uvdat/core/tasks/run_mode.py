from __future__ import annotations

from enum import StrEnum


class TaskRunMode(StrEnum):
    """How a Celery task should be executed (avoids boolean-trap call sites)."""

    ASYNC = "async"
    SYNC = "sync"
