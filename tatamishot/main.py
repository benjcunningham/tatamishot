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


def _selected_audio_ids(session: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for media in session.get("Media", []):
        for part in media.get("Part", []):
            for stream in part.get("Stream", []):
                if stream.get("streamType") == 2 and stream.get("selected"):
                    sid = str(stream.get("id", ""))
                    if sid:
                        ids.add(sid)
    return ids


def _parse_media_metadata(
    meta: dict[str, Any], selected_ids: set[str]
) -> tuple[str | None, list[dict[str, Any]], int | None]:
    file_path: str | None = None
    audio_streams: list[dict[str, Any]] = []
    audio_stream_index: int | None = None

    for media in meta.get("Media", []):
        for part in media.get("Part", []):
            if not file_path and part.get("file"):
                file_path = part["file"]
            for stream in part.get("Stream", []):
                if stream.get("streamType") != 2:
                    continue
                sid = str(stream.get("id", ""))
                is_selected = sid in selected_ids or bool(stream.get("selected"))
                entry: dict[str, Any] = {
                    "index": stream.get("index"),
                    "label": stream.get("displayTitle") or stream.get("title") or f"Track {stream.get('index')}",
                    "selected": is_selected,
                }
                audio_streams.append(entry)
                if is_selected and audio_stream_index is None:
                    audio_stream_index = entry["index"]

    return file_path, audio_streams, audio_stream_index


@app.get("/session")
async def get_session() -> JSONResponse:
    """Return the currently active Plex session."""
    plex_headers = {"X-Plex-Token": settings.plex_token, "Accept": "application/json"}
    no_cache = {"Cache-Control": "no-store"}

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{settings.plex_url}/status/sessions",
                headers=plex_headers,
                timeout=5,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Plex unreachable: {exc}") from exc

    sessions = resp.json().get("MediaContainer", {}).get("Metadata", [])
    logger.info("plex sessions count: %d", len(sessions))

    if not sessions:
        return JSONResponse({"playing": False}, headers=no_cache)

    session = sessions[0]
    logger.info(
        "plex session type=%s title=%r ratingKey=%s",
        session.get("type"), session.get("title"), session.get("ratingKey"),
    )

    selected_ids = _selected_audio_ids(session)
    logger.info("selected audio stream ids from session: %s", selected_ids)

    file_path: str | None = None
    audio_streams: list[dict[str, Any]] = []
    audio_stream_index: int | None = None

    rating_key = session.get("ratingKey")
    if rating_key:
        try:
            meta_resp = await httpx.AsyncClient().get(
                f"{settings.plex_url}/library/metadata/{rating_key}",
                headers=plex_headers,
                timeout=5,
            )
            meta_resp.raise_for_status()
            meta = meta_resp.json().get("MediaContainer", {}).get("Metadata", [{}])[0]
        except (httpx.HTTPError, IndexError, KeyError) as exc:
            logger.warning("failed to fetch library metadata for %s: %s", rating_key, exc)
            meta = {}

        file_path, audio_streams, audio_stream_index = _parse_media_metadata(meta, selected_ids)

    logger.info(
        "resolved file_path=%r audio_streams=%d audio_stream_index=%r",
        file_path, len(audio_streams), audio_stream_index,
    )

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
            "-ss", str(req.start),
            "-to", str(req.end),
            "-i", file_path,
            *audio_map,
            "-c:v", "copy",
            "-c:a", "aac",
            "-y", str(out_path),
        ]
    else:
        cmd = [
            "ffmpeg",
            "-i", file_path,
            "-ss", str(req.start),
            "-to", str(req.end),
            *audio_map,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-y", str(out_path),
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
