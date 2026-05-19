from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tatamishot.ffmpeg import _shift_srt_timestamps, _translate_path, _validate_path


if TYPE_CHECKING:
    from pathlib import Path


def test_translate_path_no_op_when_host_dir_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tatamishot.ffmpeg.settings.media_dir_host", "")
    monkeypatch.setattr("tatamishot.ffmpeg.settings.media_dir", "/media")
    assert _translate_path("/mnt/media/movie.mkv") == "/mnt/media/movie.mkv"


def test_translate_path_rewrites_host_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tatamishot.ffmpeg.settings.media_dir_host", "/mnt/media")
    monkeypatch.setattr("tatamishot.ffmpeg.settings.media_dir", "/media")
    assert _translate_path("/mnt/media/movies/film.mkv") == "/media/movies/film.mkv"


def test_translate_path_no_op_when_path_does_not_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tatamishot.ffmpeg.settings.media_dir_host", "/mnt/media")
    monkeypatch.setattr("tatamishot.ffmpeg.settings.media_dir", "/media")
    assert _translate_path("/other/path/film.mkv") == "/other/path/film.mkv"


def test_validate_path_raises_422_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(Exception) as exc_info:
        _validate_path(str(tmp_path / "nonexistent.mkv"))
    assert exc_info.value.status_code == 422  # type: ignore[attr-defined]


def test_validate_path_passes_for_existing_file(tmp_path: Path) -> None:
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"data")
    _validate_path(str(f))


def test_shift_srt_timestamps_zero_shift_unchanged() -> None:
    content = "1\n00:00:01,000 --> 00:00:03,000\nHello\n"
    assert _shift_srt_timestamps(content, 0) == content


def test_shift_srt_timestamps_positive_shift() -> None:
    content = "1\n00:00:01,000 --> 00:00:03,000\nHello\n"
    result = _shift_srt_timestamps(content, 1.5)
    assert "00:00:02,500 --> 00:00:04,500" in result


def test_shift_srt_timestamps_negative_shift() -> None:
    content = "1\n00:00:02,000 --> 00:00:04,000\nHello\n"
    result = _shift_srt_timestamps(content, -1.0)
    assert "00:00:01,000 --> 00:00:03,000" in result


def test_shift_srt_timestamps_clamps_to_zero() -> None:
    content = "1\n00:00:00,500 --> 00:00:01,000\nHello\n"
    result = _shift_srt_timestamps(content, -2.0)
    assert "00:00:00,000" in result
