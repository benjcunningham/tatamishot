from typing import Any


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
