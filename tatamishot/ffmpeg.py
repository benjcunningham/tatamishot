import logging
import subprocess
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from tatamishot.config import settings
from tatamishot.models import ClipRequest, JobStatus


logger = logging.getLogger(__name__)

jobs: dict[str, dict[str, Any]] = {}


def _translate_path(file_path: str) -> str:
    """Rewrite a host media path to its container mount point."""
    if settings.media_dir_host and file_path.startswith(settings.media_dir_host):
        return settings.media_dir_container + file_path[len(settings.media_dir_host) :]
    return file_path


def _validate_path(file_path: str) -> None:
    """Minimal guard: path must exist and be a file (server-side check)."""
    if not Path(file_path).is_file():
        raise HTTPException(status_code=422, detail=f"File not found on server: {file_path}")


def _run_clip_ffmpeg(job_id: str, file_path: str, req: ClipRequest, out_path: Path) -> None:
    jobs[job_id]["status"] = JobStatus.running

    audio_map = ["-map", "0:v:0", "-map", f"0:{req.audio_stream_index}"] if req.audio_stream_index is not None else []

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
            "-c:v",
            "copy",
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
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-y",
            str(out_path),
        ]

    logger.info("clip cmd: %s", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        jobs[job_id]["status"] = JobStatus.error
        jobs[job_id]["error"] = result.stderr.decode(errors="replace")[-500:]
    else:
        jobs[job_id]["status"] = JobStatus.done
        jobs[job_id]["filename"] = out_path.name
