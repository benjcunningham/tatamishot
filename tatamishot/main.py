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
from fastapi.responses import FileResponse
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


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"


@app.get("/session")
async def get_session() -> dict[str, Any]:
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

    if not sessions:
        return {"playing": False}

    session = sessions[0]

    file_path: str | None = None
    for media in session.get("Media", []):
        for part in media.get("Part", []):
            if part.get("file"):
                file_path = part["file"]
                break
        if file_path:
            break

    view_offset_ms: int = session.get("viewOffset", 0)

    return {
        "playing": True,
        "title": session.get("title", "Unknown"),
        "grandparent_title": session.get("grandparentTitle"),
        "year": session.get("year"),
        "thumb": session.get("thumb"),
        "file_path": file_path,
        "timestamp": view_offset_ms / 1000,
        "duration": session.get("duration", 0) / 1000,
    }


@app.post("/frame")
async def extract_frame(req: FrameRequest) -> FileResponse:
    """Extract a single frame and return it as a JPEG."""
    _validate_path(req.file_path)

    job_id = uuid.uuid4().hex
    out_path = Path(settings.output_dir) / f"{job_id}.jpg"

    cmd = [
        "ffmpeg",
        "-ss",
        str(req.timestamp),
        "-i",
        req.file_path,
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


def _run_clip_ffmpeg(job_id: str, req: ClipRequest, out_path: Path) -> None:
    jobs[job_id]["status"] = JobStatus.running

    if req.fast:
        cmd = [
            "ffmpeg",
            "-ss",
            str(req.start),
            "-to",
            str(req.end),
            "-i",
            req.file_path,
            "-c",
            "copy",
            "-y",
            str(out_path),
        ]
    else:
        cmd = [
            "ffmpeg",
            "-i",
            req.file_path,
            "-ss",
            str(req.start),
            "-to",
            str(req.end),
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
    _validate_path(req.file_path)

    if req.end <= req.start:
        raise HTTPException(status_code=422, detail="end must be greater than start")

    job_id = uuid.uuid4().hex
    out_path = Path(settings.output_dir) / f"{job_id}.mp4"

    jobs[job_id] = {"status": JobStatus.pending, "filename": None, "error": None}
    background_tasks.add_task(_run_clip_ffmpeg, job_id, req, out_path)

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


def _validate_path(file_path: str) -> None:
    """Minimal guard: path must exist and be a file (server-side check)."""
    if not Path(file_path).is_file():
        raise HTTPException(status_code=422, detail=f"File not found on server: {file_path}")
