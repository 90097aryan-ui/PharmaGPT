"""
services/job_runner.py — Strategy interface for background job execution.

Today (confirmed with the user): no Redis/Celery in this stack, so
ThreadPoolJobRunner (an in-process concurrent.futures.ThreadPoolExecutor) is
the active implementation. Job status is never held in memory — it is
persisted to SQLite (see database.py) — so it survives independently of
which thread or gunicorn worker process picks up the work, and is visible to
any process that reads the DB.

Future: swap to Celery + Redis by implementing CeleryJobRunner.submit() and
changing the one line that constructs `job_runner` below. No route or
business logic anywhere else needs to change — this is the entire point of
depending on the JobRunner interface rather than on ThreadPoolExecutor
directly.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from pharmagpt.config import EXTRACTION_WORKERS

logger = logging.getLogger(__name__)


class JobRunner(ABC):
    """Strategy interface: "run this function in the background, somehow"."""

    @abstractmethod
    def submit(self, fn: Callable, *args, **kwargs) -> None:
        raise NotImplementedError


class ThreadPoolJobRunner(JobRunner):
    """
    Active implementation: runs jobs on a small in-process thread pool.

    Suitable for the current single-SQLite-file, no-extra-infra deployment.
    Exceptions raised inside `fn` are caught and logged here so a crashed
    background job can never take down the web process or silently vanish.
    """

    def __init__(self, max_workers: int = EXTRACTION_WORKERS):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="doc-extract-job",
        )

    def submit(self, fn: Callable, *args, **kwargs) -> None:
        def _wrapped():
            try:
                fn(*args, **kwargs)
            except Exception:
                logger.exception("Background job %s raised an unhandled exception", fn)

        self._executor.submit(_wrapped)


class CeleryJobRunner(JobRunner):
    """
    Future extension point. Left unimplemented on purpose: adding Celery +
    Redis is an infrastructure decision (new service, new dependency, new
    Render cost) that should be made deliberately, not smuggled in as a side
    effect of this refactor. Implementing this class and pointing
    `job_runner` at it is the entire migration.
    """

    def submit(self, fn: Callable, *args, **kwargs) -> None:
        raise NotImplementedError(
            "CeleryJobRunner is a future extension point — see "
            "SYSTEM_ARCHITECTURE_DOCUMENT_PROCESSING.md roadmap."
        )


# Module-level singleton used by services/document_processor.py. Swapping
# execution backends is a one-line change here.
job_runner: JobRunner = ThreadPoolJobRunner()
