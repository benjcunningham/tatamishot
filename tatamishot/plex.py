from typing import Any

from pydantic import BaseModel, Field


TEXT_SUBTITLE_CODECS = {"srt", "subrip", "ass", "ssa", "webvtt", "mov_text", "text"}


class ParsedMedia(BaseModel):
    file_path: str | None = None
    fps: float = 24.0
    audio_streams: list[dict[str, Any]] = Field(default_factory=list)
    audio_stream_index: int | None = None
    subtitle_streams: list[dict[str, Any]] = Field(default_factory=list)
    subtitle_stream_index: int | None = None
    subtitle_offset: float = 0.0


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


def _selected_subtitle_ids(session: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for media in session.get("Media", []):
        for part in media.get("Part", []):
            for stream in part.get("Stream", []):
                if stream.get("streamType") == 3 and stream.get("selected"):
                    sid = str(stream.get("id", ""))
                    if sid:
                        ids.add(sid)
    return ids


def _subtitle_offset_from_session(session: dict[str, Any]) -> float:
    """Return the user's subtitle offset in seconds from a Plex session (default 0)."""
    for media in session.get("Media", []):
        for part in media.get("Part", []):
            for stream in part.get("Stream", []):
                if stream.get("streamType") == 3 and stream.get("selected"):
                    offset_ms = stream.get("subtitleOffset", 0)
                    return int(offset_ms) / 1000.0
    return 0.0


def _parse_media_metadata(
    meta: dict[str, Any], selected_audio_ids: set[str], selected_subtitle_ids: set[str]
) -> ParsedMedia:
    result = ParsedMedia()

    for media in meta.get("Media", []):
        for part in media.get("Part", []):
            if not result.file_path and part.get("file"):
                result.file_path = part["file"]
            for stream in part.get("Stream", []):
                stream_type = stream.get("streamType")

                if stream_type == 1 and result.fps == 24.0:
                    try:
                        result.fps = float(stream.get("frameRate", 24.0))
                    except (TypeError, ValueError):
                        pass

                elif stream_type == 2:
                    sid = str(stream.get("id", ""))
                    is_selected = sid in selected_audio_ids or bool(stream.get("selected"))
                    entry: dict[str, Any] = {
                        "index": stream.get("index"),
                        "label": stream.get("displayTitle") or stream.get("title") or f"Track {stream.get('index')}",
                        "selected": is_selected,
                    }
                    result.audio_streams.append(entry)
                    if is_selected and result.audio_stream_index is None:
                        result.audio_stream_index = entry["index"]

                elif stream_type == 3:
                    sid = str(stream.get("id", ""))
                    is_selected = sid in selected_subtitle_ids or bool(stream.get("selected"))
                    codec = str(stream.get("codec", "")).lower()
                    entry_sub: dict[str, Any] = {
                        "index": stream.get("index"),
                        "label": stream.get("displayTitle") or stream.get("title") or f"Subtitle {stream.get('index')}",
                        "selected": is_selected,
                        "codec": codec,
                        "burnable": codec in TEXT_SUBTITLE_CODECS,
                    }
                    result.subtitle_streams.append(entry_sub)
                    if is_selected and result.subtitle_stream_index is None:
                        result.subtitle_stream_index = entry_sub["index"]

    return result
