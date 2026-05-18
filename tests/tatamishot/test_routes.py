from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from tatamishot.ffmpeg import jobs
from tatamishot.main import app as fastapi_app


if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def clear_jobs() -> None:
    jobs.clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(fastapi_app)


def test_job_status_404_for_unknown_job(client: TestClient) -> None:
    resp = client.get("/jobs/doesnotexist")
    assert resp.status_code == 404


def test_job_status_returns_job(client: TestClient) -> None:
    jobs["abc123"] = {"status": "running", "filename": None, "error": None}
    resp = client.get("/jobs/abc123")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_output_404_for_unknown_job(client: TestClient) -> None:
    resp = client.get("/output/doesnotexist")
    assert resp.status_code == 404


def test_output_409_when_job_not_done(client: TestClient) -> None:
    jobs["abc"] = {"status": "running", "filename": None, "error": None}
    resp = client.get("/output/abc")
    assert resp.status_code == 409


def test_output_404_when_file_missing_from_disk(client: TestClient) -> None:
    jobs["abc"] = {"status": "done", "filename": "abc.mp4", "error": None}
    resp = client.get("/output/abc")
    assert resp.status_code == 404


def test_clip_422_when_end_before_start(tmp_path: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"data")
    monkeypatch.setattr("tatamishot.ffmpeg.settings.media_dir", "")
    monkeypatch.setattr("tatamishot.ffmpeg.settings.output_dir", str(tmp_path))
    resp = client.post("/clip", json={"file_path": str(f), "start": 10.0, "end": 5.0})
    assert resp.status_code == 422


def test_clip_422_when_file_missing(client: TestClient) -> None:
    resp = client.post("/clip", json={"file_path": "/nonexistent.mkv", "start": 0.0, "end": 5.0})
    assert resp.status_code == 422


def test_frame_422_when_file_missing(client: TestClient) -> None:
    resp = client.post("/frame", json={"file_path": "/nonexistent.mkv", "timestamp": 10.0})
    assert resp.status_code == 422
