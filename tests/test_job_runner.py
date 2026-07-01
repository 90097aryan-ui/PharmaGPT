"""
tests/test_job_runner.py — Unit tests for services/job_runner.py's Strategy
implementations.
"""

import time

import pytest

from pharmagpt.services.job_runner import CeleryJobRunner, ThreadPoolJobRunner


def test_threadpool_job_runner_executes_submitted_function():
    runner = ThreadPoolJobRunner(max_workers=1)
    results = []

    runner.submit(lambda x: results.append(x * 2), 21)

    for _ in range(20):
        if results:
            break
        time.sleep(0.05)

    assert results == [42]


def test_threadpool_job_runner_swallows_exceptions_without_crashing():
    runner = ThreadPoolJobRunner(max_workers=1)

    def boom():
        raise RuntimeError("simulated crash")

    # Must not raise here — a crashing job must never take down the caller.
    runner.submit(boom)

    # A second, well-behaved job submitted right after must still run,
    # proving the pool itself is unaffected by the first job's exception.
    results = []
    runner.submit(lambda: results.append("ok"))
    for _ in range(20):
        if results:
            break
        time.sleep(0.05)
    assert results == ["ok"]


def test_celery_job_runner_is_an_unimplemented_future_extension_point():
    runner = CeleryJobRunner()
    with pytest.raises(NotImplementedError):
        runner.submit(lambda: None)
