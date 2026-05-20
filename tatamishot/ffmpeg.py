import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from tatamishot.config import settings
from tatamishot.models import ClipRequest, JobStatus


logger = logging.getLogger(__name__)

jobs: dict[str, dict[str, Any]] = {}

TEXT_SUBTITLE_CODECS = {"srt", "subrip", "ass", "ssa", "webvtt", "mov_text", "text"}


def _translate_path(file_path: str) -> str:
    """Rewrite a host media path to its container mount point."""
    if settings.media_dir_host and file_path.startswith(settings.media_dir_host):
        return settings.media_dir + file_path[len(settings.media_dir_host) :]
    return file_path


def _validate_path(file_path: str) -> None:
    """Minimal guard: path must exist and be a file (server-side check)."""
    if not Path(file_path).is_file():
        raise HTTPException(status_code=422, detail=f"File not found on server: {file_path}")


def _shift_srt_timestamps(content: str, shift_seconds: float) -> str:
    """Shift all SRT timestamps by shift_seconds (may be negative)."""
    delta_ms = int(shift_seconds * 1000)

    def shift_ts(match: re.Match[str]) -> str:
        h, m, s_ms = match.group().split(":")
        s, ms = s_ms.split(",")
        total = int(h) * 3_600_000 + int(m) * 60_000 + int(s) * 1_000 + int(ms) + delta_ms
        total = max(0, total)
        h2, rem = divmod(total, 3_600_000)
        m2, rem = divmod(rem, 60_000)
        s2, ms2 = divmod(rem, 1_000)
        return f"{h2:02d}:{m2:02d}:{s2:02d},{ms2:03d}"

    return re.sub(r"\d{2}:\d{2}:\d{2},\d{3}", shift_ts, content)


def _extract_shifted_srt(file_path: str, stream_index: int, shift_seconds: float) -> str | None:
    """Extract a subtitle stream as SRT and apply a timestamp shift.

    Returns the path to a temp file, or None if extraction fails (e.g. image-based subs).
    Caller is responsible for deleting the temp file.
    """
    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as f:
        raw_path = f.name

    result = subprocess.run(
        ["ffmpeg", "-i", file_path, "-map", f"0:{stream_index}", "-c:s", "srt", "-y", raw_path],
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        logger.warning(
            "subtitle extraction failed for stream %d: %s",
            stream_index,
            result.stderr.decode(errors="replace")[-200:],
        )
        try:
            os.unlink(raw_path)
        except OSError:
            pass
        return None

    with open(raw_path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    os.unlink(raw_path)

    shifted = _shift_srt_timestamps(content, shift_seconds) if shift_seconds != 0 else content

    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False, mode="w", encoding="utf-8") as f:
        f.write(shifted)
        return f.name


def _run_clip_ffmpeg(job_id: str, file_path: str, req: ClipRequest, out_path: Path) -> None:
    jobs[job_id]["status"] = JobStatus.running

    srt_path: str | None = None
    if req.subtitle_stream_index is not None:
        srt_path = _extract_shifted_srt(file_path, req.subtitle_stream_index, req.subtitle_offset - req.start)

    audio_map = ["-map", "0:v:0", "-map", f"0:{req.audio_stream_index}"] if req.audio_stream_index is not None else []
    subtitle_filter = ["-vf", f"subtitles={srt_path}"] if srt_path else []
    video_codec = "libx264" if srt_path else "copy"

    if req.fast:
        cmd = [
            "ffmpeg",
            "-ss",
            str(req.start),
            "-to",
            str(req.end),
            "-i",
            file_path,
            *audio_map,
            *subtitle_filter,
            "-c:v",
            video_codec,
            "-c:a",
            "aac",
            "-y",
            str(out_path),
        ]
    else:
        cmd = [
            "ffmpeg",
            "-i",
            file_path,
            "-ss",
            str(req.start),
            "-to",
            str(req.end),
            *audio_map,
            *subtitle_filter,
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-y",
            str(out_path),
        ]

    logger.info("clip cmd: %s", " ".join(cmd))

    try:
        result = subprocess.run(cmd, capture_output=True, check=False)
        if result.returncode != 0:
            jobs[job_id]["status"] = JobStatus.error
            jobs[job_id]["error"] = result.stderr.decode(errors="replace")[-500:]
        else:
            jobs[job_id]["status"] = JobStatus.done
            jobs[job_id]["filename"] = out_path.name
    finally:
        if srt_path:
            try:
                os.unlink(srt_path)
            except OSError:
                pass
