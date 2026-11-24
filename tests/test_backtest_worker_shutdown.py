import threading

from sigmarail_studio_mcp.backtest_runner import worker


def test_worker_shutdown_cancels_active_job(monkeypatch):
    run_finished = threading.Event()
    cancelled = []
    monkeypatch.setattr(worker, "_STOP", False)

    def cancel_job(job_id):
        cancelled.append(job_id)
        return {"job_id": job_id, "status": "cancelled", "cancelled": True}

    watcher = threading.Thread(
        target=worker._cancel_job_on_shutdown,
        args=("job-123", run_finished, cancel_job),
    )
    watcher.start()
    monkeypatch.setattr(worker, "_STOP", True)
    watcher.join(timeout=2)

    assert not watcher.is_alive()
    assert cancelled == ["job-123"]


def test_completed_job_is_not_cancelled_during_worker_shutdown(monkeypatch):
    run_finished = threading.Event()
    run_finished.set()
    cancelled = []
    monkeypatch.setattr(worker, "_STOP", True)

    worker._cancel_job_on_shutdown(
        "job-123",
        run_finished,
        lambda job_id: cancelled.append(job_id),
    )

    assert cancelled == []


def test_worker_shutdown_retries_cancel_after_transient_error(monkeypatch):
    run_finished = threading.Event()
    calls = []
    monkeypatch.setattr(worker, "_STOP", True)

    def cancel_job(job_id):
        calls.append(job_id)
        if len(calls) == 1:
            return {"error": "database temporarily unavailable"}
        return {"job_id": job_id, "status": "cancelled", "cancelled": True}

    watcher = threading.Thread(
        target=worker._cancel_job_on_shutdown,
        args=("job-123", run_finished, cancel_job),
    )
    watcher.start()
    watcher.join(timeout=2)

    assert not watcher.is_alive()
    assert calls == ["job-123", "job-123"]
