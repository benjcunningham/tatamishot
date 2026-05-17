import asyncio
import logging
import os
import subprocess
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from enum import StrEnum
from pathlib import Path
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tatamishot.config import settings


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

jobs: dict[str, dict[str, Any]] = {}


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    os.makedirs(settings.output_dir, exist_ok=True)
    yield


app = FastAPI(title="TatamiShot", lifespan=lifespan)


class FrameRequest(BaseModel):
    file_path: str
    timestamp: float


class ClipRequest(BaseModel):
    file_path: str
    start: float
    end: float
    fast: bool = True
    audio_stream_index: int | None = None


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"


@app.get("/session")
async def get_session() -> JSONResponse:
    """Return the currently active Plex session."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{settings.plex_url}/status/sessions",
                headers={
                    "X-Plex-Token": settings.plex_token,
                    "Accept": "application/json",
                },
                timeout=5,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Plex unreachable: {exc}") from exc

    data = resp.json()
    media_container = data.get("MediaContainer", {})
    sessions = media_container.get("Metadata", [])

    no_cache = {"Cache-Control": "no-store"}

    logger.info("plex sessions count: %d", len(sessions))

    if not sessions:
        return JSONResponse({"playing": False}, headers=no_cache)

    session = sessions[0]
    logger.info("plex session type=%s title=%r", session.get("type"), session.get("title"))

    file_path: str | None = None
    audio_streams: list[dict[str, Any]] = []
    audio_stream_index: int | None = None

    for media_idx, media in enumerate(session.get("Media", [])):
        for part_idx, part in enumerate(media.get("Part", [])):
            part_file = part.get("file")
            stream_count = len(part.get("Stream", []))
            logger.info(
                "  media[%d].part[%d]: file=%r streams=%d keys=%s",
                media_idx, part_idx, part_file, stream_count, sorted(part.keys()),
            )
            if not file_path and part_file:
                file_path = part_file
            for stream in part.get("Stream", []):
                if stream.get("streamType") != 2:
                    continue
                logger.info("  raw audio stream keys=%s data=%r", sorted(stream.keys()), stream)
                entry: dict[str, Any] = {
                    "index": stream.get("index"),
                    "label": stream.get("displayTitle") or stream.get("title") or f"Track {stream.get('index')}",
                    "selected": bool(stream.get("selected")),
                }
                logger.info(
                    "  audio stream: index=%s label=%r selected=%s",
                    entry["index"], entry["label"], entry["selected"],
                )
                audio_streams.append(entry)
                if entry["selected"]:
                    audio_stream_index = entry["index"]

    logger.info("resolved file_path=%r audio_stream_index=%r", file_path, audio_stream_index)

    view_offset_ms: int = session.get("viewOffset", 0)

    return JSONResponse(
        {
            "playing": True,
            "title": session.get("title", "Unknown"),
            "grandparent_title": session.get("grandparentTitle"),
            "year": session.get("year"),
            "thumb": session.get("thumb"),
            "file_path": file_path,
            "timestamp": view_offset_ms / 1000,
            "duration": session.get("duration", 0) / 1000,
            "audio_streams": audio_streams,
            "audio_stream_index": audio_stream_index,
        },
        headers=no_cache,
    )


@app.post("/frame")
async def extract_frame(req: FrameRequest) -> FileResponse:
    """Extract a single frame and return it as a JPEG."""
    file_path = _translate_path(req.file_path)
    _validate_path(file_path)

    job_id = uuid.uuid4().hex
    out_path = Path(settings.output_dir) / f"{job_id}.jpg"

    cmd = [
        "ffmpeg",
        "-ss",
        str(req.timestamp),
        "-i",
        file_path,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        "-y",
        str(out_path),
    ]

    logger.info("frame cmd: %s", " ".join(cmd))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="ffmpeg timed out") from exc

    if proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"ffmpeg error: {stderr.decode(errors='replace')[-500:]}",
        )

    return FileResponse(str(out_path), media_type="image/jpeg", filename=f"{job_id}.jpg")


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
            "-c",
            "copy",
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


@app.post("/clip")
async def extract_clip(req: ClipRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Enqueue a clip extraction job and return a job ID for polling."""
    file_path = _translate_path(req.file_path)
    _validate_path(file_path)

    if req.end <= req.start:
        raise HTTPException(status_code=422, detail="end must be greater than start")

    job_id = uuid.uuid4().hex
    out_path = Path(settings.output_dir) / f"{job_id}.mp4"

    jobs[job_id] = {"status": JobStatus.pending, "filename": None, "error": None}
    background_tasks.add_task(_run_clip_ffmpeg, job_id, file_path, req, out_path)

    return {"job_id": job_id, "status": JobStatus.pending}


@app.get("/jobs/{job_id}")
async def job_status(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, **job}


@app.get("/output/{job_id}")
async def download_output(job_id: str) -> FileResponse:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != JobStatus.done:
        raise HTTPException(status_code=409, detail=f"Job status: {job['status']}")

    filename = job["filename"]
    out_path = Path(settings.output_dir) / filename
    if not out_path.exists():
        raise HTTPException(status_code=404, detail="Output file missing")

    media_type = "video/mp4" if filename.endswith(".mp4") else "image/jpeg"
    return FileResponse(str(out_path), media_type=media_type, filename=filename)


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")


def _translate_path(file_path: str) -> str:
    """Rewrite a host media path to its container mount point."""
    if settings.media_dir_host and file_path.startswith(settings.media_dir_host):
        return settings.media_dir_container + file_path[len(settings.media_dir_host) :]
    return file_path


def _validate_path(file_path: str) -> None:
    """Minimal guard: path must exist and be a file (server-side check)."""
    if not Path(file_path).is_file():
        raise HTTPException(status_code=422, detail=f"File not found on server: {file_path}")
