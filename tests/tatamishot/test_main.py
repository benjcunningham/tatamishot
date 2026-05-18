from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient


if TYPE_CHECKING:
    from pathlib import Path

from tatamishot.main import (
    _parse_media_metadata,
    _selected_audio_ids,
    _translate_path,
    _validate_path,
    jobs,
)
from tatamishot.main import app as fastapi_app


@pytest.fixture(autouse=True)
def clear_jobs() -> None:
    jobs.clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(fastapi_app)


def test_selected_audio_ids_empty_session() -> None:
    assert _selected_audio_ids({}) == set()


def test_selected_audio_ids_no_selected_streams() -> None:
    session = {"Media": [{"Part": [{"Stream": [{"streamType": 2, "id": "1", "selected": False}]}]}]}
    assert _selected_audio_ids(session) == set()


def test_selected_audio_ids_returns_selected_id() -> None:
    session = {"Media": [{"Part": [{"Stream": [{"streamType": 2, "id": "42", "selected": True}]}]}]}
    assert _selected_audio_ids(session) == {"42"}


def test_selected_audio_ids_ignores_non_audio_streams() -> None:
    session = {
        "Media": [
            {
                "Part": [
                    {
                        "Stream": [
                            {"streamType": 1, "id": "10", "selected": True},
                            {"streamType": 2, "id": "11", "selected": True},
                        ]
                    }
                ]
            }
        ]
    }
    assert _selected_audio_ids(session) == {"11"}


def test_selected_audio_ids_multiple_selected() -> None:
    session = {
        "Media": [
            {
                "Part": [
                    {
                        "Stream": [
                            {"streamType": 2, "id": "1", "selected": True},
                            {"streamType": 2, "id": "2", "selected": True},
                        ]
                    }
                ]
            }
        ]
    }
    assert _selected_audio_ids(session) == {"1", "2"}


def test_selected_audio_ids_skips_empty_id() -> None:
    session = {"Media": [{"Part": [{"Stream": [{"streamType": 2, "id": "", "selected": True}]}]}]}
    assert _selected_audio_ids(session) == set()


def test_parse_media_metadata_empty() -> None:
    fp, streams, idx = _parse_media_metadata({}, set())
    assert fp is None
    assert streams == []
    assert idx is None


def test_parse_media_metadata_extracts_file_path() -> None:
    meta = {"Media": [{"Part": [{"file": "/media/movie.mkv", "Stream": []}]}]}
    fp, _, _ = _parse_media_metadata(meta, set())
    assert fp == "/media/movie.mkv"


def test_parse_media_metadata_skips_non_audio_streams() -> None:
    meta = {
        "Media": [{"Part": [{"file": "/f.mkv", "Stream": [{"streamType": 1, "id": "1", "index": 0}]}]}]
    }
    _, streams, _ = _parse_media_metadata(meta, set())
    assert streams == []


def test_parse_media_metadata_marks_stream_selected_by_id() -> None:
    meta = {
        "Media": [
            {
                "Part": [
                    {
                        "file": "/f.mkv",
                        "Stream": [
                            {"streamType": 2, "id": "99", "index": 1, "displayTitle": "English", "selected": False}
                        ],
                    }
                ]
            }
        ]
    }
    _, streams, idx = _parse_media_metadata(meta, {"99"})
    assert streams[0]["selected"] is True
    assert idx == 1


def test_parse_media_metadata_marks_stream_selected_by_flag() -> None:
    meta = {
        "Media": [
            {
                "Part": [
                    {
                        "file": "/f.mkv",
                        "Stream": [
                            {"streamType": 2, "id": "5", "index": 2, "displayTitle": "French", "selected": True}
                        ],
                    }
                ]
            }
        ]
    }
    _, streams, idx = _parse_media_metadata(meta, set())
    assert streams[0]["selected"] is True
    assert idx == 2


def test_parse_media_metadata_label_falls_back_to_title() -> None:
    meta = {
        "Media": [
            {
                "Part": [
                    {
                        "file": "/f.mkv",
                        "Stream": [{"streamType": 2, "id": "1", "index": 1, "displayTitle": "", "title": "Alt"}],
                    }
                ]
            }
        ]
    }
    _, streams, _ = _parse_media_metadata(meta, set())
    assert streams[0]["label"] == "Alt"


def test_parse_media_metadata_label_falls_back_to_track_number() -> None:
    meta = {
        "Media": [
            {
                "Part": [
                    {
                        "file": "/f.mkv",
                        "Stream": [{"streamType": 2, "id": "1", "index": 3, "displayTitle": "", "title": ""}],
                    }
                ]
            }
        ]
    }
    _, streams, _ = _parse_media_metadata(meta, set())
    assert streams[0]["label"] == "Track 3"


def test_parse_media_metadata_audio_index_set_to_first_selected() -> None:
    meta = {
        "Media": [
            {
                "Part": [
                    {
                        "file": "/f.mkv",
                        "Stream": [
                            {"streamType": 2, "id": "1", "index": 1, "displayTitle": "A", "selected": True},
                            {"streamType": 2, "id": "2", "index": 2, "displayTitle": "B", "selected": True},
                        ],
                    }
                ]
            }
        ]
    }
    _, _, idx = _parse_media_metadata(meta, set())
    assert idx == 1


def test_translate_path_no_op_when_host_dir_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tatamishot.main.settings.media_dir_host", "")
    monkeypatch.setattr("tatamishot.main.settings.media_dir_container", "/media")
    assert _translate_path("/mnt/media/movie.mkv") == "/mnt/media/movie.mkv"


def test_translate_path_rewrites_host_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tatamishot.main.settings.media_dir_host", "/mnt/media")
    monkeypatch.setattr("tatamishot.main.settings.media_dir_container", "/media")
    assert _translate_path("/mnt/media/movies/film.mkv") == "/media/movies/film.mkv"


def test_translate_path_no_op_when_path_does_not_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tatamishot.main.settings.media_dir_host", "/mnt/media")
    monkeypatch.setattr("tatamishot.main.settings.media_dir_container", "/media")
    assert _translate_path("/other/path/film.mkv") == "/other/path/film.mkv"


def test_validate_path_raises_422_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(Exception) as exc_info:
        _validate_path(str(tmp_path / "nonexistent.mkv"))
    assert exc_info.value.status_code == 422  # type: ignore[attr-defined]


def test_validate_path_passes_for_existing_file(tmp_path: Path) -> None:
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"data")
    _validate_path(str(f))


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
    monkeypatch.setattr("tatamishot.main.settings.media_dir_host", "")
    monkeypatch.setattr("tatamishot.main.settings.output_dir", str(tmp_path))
    resp = client.post("/clip", json={"file_path": str(f), "start": 10.0, "end": 5.0})
    assert resp.status_code == 422


def test_clip_422_when_file_missing(client: TestClient) -> None:
    resp = client.post("/clip", json={"file_path": "/nonexistent.mkv", "start": 0.0, "end": 5.0})
    assert resp.status_code == 422


def test_frame_422_when_file_missing(client: TestClient) -> None:
    resp = client.post("/frame", json={"file_path": "/nonexistent.mkv", "timestamp": 10.0})
    assert resp.status_code == 422
