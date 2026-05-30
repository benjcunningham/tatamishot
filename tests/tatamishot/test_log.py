from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import structlog
from fastapi.testclient import TestClient

from tatamishot.ffmpeg import _run_clip_ffmpeg, jobs
from tatamishot.log import configure_logging
from tatamishot.main import app as fastapi_app
from tatamishot.models import ClipRequest, JobStatus


if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def clear_jobs() -> None:
    jobs.clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(fastapi_app)


def test_configure_logging_installs_processor_formatter() -> None:
    configure_logging()
    root = logging.getLogger()
    assert any(isinstance(h.formatter, structlog.stdlib.ProcessorFormatter) for h in root.handlers)


def test_middleware_binds_generated_request_id(client: TestClient) -> None:
    with patch("structlog.contextvars.bind_contextvars") as mock_bind:
        client.get("/jobs/notreal")

    mock_bind.assert_called_once()
    kwargs = mock_bind.call_args.kwargs
    assert "X-Request-ID" in kwargs
    assert kwargs["X-Request-ID"]


def test_middleware_binds_method_and_path(client: TestClient) -> None:
    with patch("structlog.contextvars.bind_contextvars") as mock_bind:
        client.get("/jobs/notreal")

    kwargs = mock_bind.call_args.kwargs
    assert kwargs["method"] == "GET"
    assert kwargs["path"] == "/jobs/notreal"


def test_middleware_uses_provided_request_id(client: TestClient) -> None:
    with patch("structlog.contextvars.bind_contextvars") as mock_bind:
        client.get("/jobs/notreal", headers={"X-Request-ID": "550e8400-e29b-41d4-a716-446655440000"})

    kwargs = mock_bind.call_args.kwargs
    assert str(kwargs["X-Request-ID"]) == "550e8400-e29b-41d4-a716-446655440000"


def test_middleware_binds_correlation_id(client: TestClient) -> None:
    with patch("structlog.contextvars.bind_contextvars") as mock_bind:
        client.get("/jobs/notreal", headers={"X-Correlation-ID": "660e8400-e29b-41d4-a716-446655440000"})

    kwargs = mock_bind.call_args.kwargs
    assert str(kwargs["X-Correlation-ID"]) == "660e8400-e29b-41d4-a716-446655440000"


def test_middleware_uses_provided_correlation_id_over_generated(client: TestClient) -> None:
    with patch("structlog.contextvars.bind_contextvars") as mock_bind:
        client.get("/jobs/notreal", headers={"X-Correlation-ID": "770e8400-e29b-41d4-a716-446655440000"})
    kwargs = mock_bind.call_args.kwargs
    assert str(kwargs["X-Correlation-ID"]) == "770e8400-e29b-41d4-a716-446655440000"


def test_middleware_clears_contextvars_before_each_request(client: TestClient) -> None:
    with patch("structlog.contextvars.clear_contextvars") as mock_clear:
        client.get("/jobs/notreal")
        client.get("/jobs/notreal")

    assert mock_clear.call_count == 2


def test_run_clip_ffmpeg_binds_job_id(tmp_path: Path) -> None:
    job_id = "test-job-abc"
    jobs[job_id] = {"status": JobStatus.pending, "filename": None, "error": None}
    out_path = tmp_path / f"{job_id}.mp4"
    req = ClipRequest(file_path="/fake/movie.mkv", start=0.0, end=5.0)

    with (
        patch("structlog.contextvars.bind_contextvars") as mock_bind,
        patch("tatamishot.ffmpeg.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=1, stderr=b"error")
        _run_clip_ffmpeg(job_id, "/fake/movie.mkv", req, out_path)

    mock_bind.assert_called_once_with(job_id=job_id)
