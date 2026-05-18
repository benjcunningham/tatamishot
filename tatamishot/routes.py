import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from tatamishot.config import settings
from tatamishot.ffmpeg import _run_clip_ffmpeg, _translate_path, _validate_path, jobs
from tatamishot.models import ClipRequest, FrameRequest, JobStatus
from tatamishot.plex import _parse_media_metadata, _selected_audio_ids


logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/session")
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
        session.get("type"),
        session.get("title"),
        session.get("ratingKey"),
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
        file_path,
        len(audio_streams),
        audio_stream_index,
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


@router.post("/frame")
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


@router.post("/clip")
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


@router.get("/jobs/{job_id}")
async def job_status(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, **job}


@router.get("/output/{job_id}")
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
