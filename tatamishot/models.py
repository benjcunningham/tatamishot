from enum import StrEnum

from pydantic import BaseModel


class FrameRequest(BaseModel):
    file_path: str
    timestamp: float
    subtitle_stream_index: int | None = None
    subtitle_offset: float = 0.0


class ClipRequest(BaseModel):
    file_path: str
    start: float
    end: float
    fast: bool = True
    audio_stream_index: int | None = None
    subtitle_stream_index: int | None = None
    subtitle_offset: float = 0.0


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"
