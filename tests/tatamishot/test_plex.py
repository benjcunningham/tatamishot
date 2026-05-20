from tatamishot.plex import (
    _parse_media_metadata,
    _selected_audio_ids,
    _selected_subtitle_ids,
    _subtitle_offset_from_session,
)


def test_selected_audio_ids_empty_session() -> None:
    assert _selected_audio_ids({}) == set()


def test_selected_audio_ids_no_selected_streams() -> None:
    session = {"Media": [{"Part": [{"Stream": [{"streamType": 2, "id": "1", "selected": False}]}]}]}
    assert _selected_audio_ids(session) == set()


def test_selected_audio_ids_returns_selected_id() -> None:
    session = {"Media": [{"Part": [{"Stream": [{"streamType": 2, "id": "42", "selected": True}]}]}]}
    assert _selected_audio_ids(session) == {"42"}


def test_selected_audio_ids_ignores_non_audio_streams() -> None:
    session = {
        "Media": [
            {
                "Part": [
                    {
                        "Stream": [
                            {"streamType": 1, "id": "10", "selected": True},
                            {"streamType": 2, "id": "11", "selected": True},
                        ]
                    }
                ]
            }
        ]
    }
    assert _selected_audio_ids(session) == {"11"}


def test_selected_audio_ids_multiple_selected() -> None:
    session = {
        "Media": [
            {
                "Part": [
                    {
                        "Stream": [
                            {"streamType": 2, "id": "1", "selected": True},
                            {"streamType": 2, "id": "2", "selected": True},
                        ]
                    }
                ]
            }
        ]
    }
    assert _selected_audio_ids(session) == {"1", "2"}


def test_selected_audio_ids_skips_empty_id() -> None:
    session = {"Media": [{"Part": [{"Stream": [{"streamType": 2, "id": "", "selected": True}]}]}]}
    assert _selected_audio_ids(session) == set()


def test_selected_subtitle_ids_empty_session() -> None:
    assert _selected_subtitle_ids({}) == set()


def test_selected_subtitle_ids_returns_selected_id() -> None:
    session = {"Media": [{"Part": [{"Stream": [{"streamType": 3, "id": "55", "selected": True}]}]}]}
    assert _selected_subtitle_ids(session) == {"55"}


def test_selected_subtitle_ids_ignores_non_subtitle_streams() -> None:
    session = {
        "Media": [
            {
                "Part": [
                    {
                        "Stream": [
                            {"streamType": 2, "id": "10", "selected": True},
                            {"streamType": 3, "id": "20", "selected": True},
                        ]
                    }
                ]
            }
        ]
    }
    assert _selected_subtitle_ids(session) == {"20"}


def test_subtitle_offset_from_session_no_subtitle() -> None:
    assert _subtitle_offset_from_session({}) == 0.0


def test_subtitle_offset_from_session_returns_converted_seconds() -> None:
    session = {
        "Media": [{"Part": [{"Stream": [{"streamType": 3, "id": "1", "selected": True, "subtitleOffset": 500}]}]}]
    }
    assert _subtitle_offset_from_session(session) == 0.5


def test_subtitle_offset_from_session_negative_offset() -> None:
    session = {
        "Media": [{"Part": [{"Stream": [{"streamType": 3, "id": "1", "selected": True, "subtitleOffset": -1000}]}]}]
    }
    assert _subtitle_offset_from_session(session) == -1.0


def test_parse_media_metadata_empty() -> None:
    parsed = _parse_media_metadata({}, set(), set())
    assert parsed.file_path is None
    assert parsed.audio_streams == []
    assert parsed.audio_stream_index is None
    assert parsed.subtitle_streams == []
    assert parsed.subtitle_stream_index is None


def test_parse_media_metadata_extracts_file_path() -> None:
    meta = {"Media": [{"Part": [{"file": "/media/movie.mkv", "Stream": []}]}]}
    parsed = _parse_media_metadata(meta, set(), set())
    assert parsed.file_path == "/media/movie.mkv"


def test_parse_media_metadata_skips_non_audio_streams() -> None:
    meta = {"Media": [{"Part": [{"file": "/f.mkv", "Stream": [{"streamType": 1, "id": "1", "index": 0}]}]}]}
    parsed = _parse_media_metadata(meta, set(), set())
    assert parsed.audio_streams == []


def test_parse_media_metadata_marks_stream_selected_by_id() -> None:
    meta = {
        "Media": [
            {
                "Part": [
                    {
                        "file": "/f.mkv",
                        "Stream": [
                            {"streamType": 2, "id": "99", "index": 1, "displayTitle": "English", "selected": False}
                        ],
                    }
                ]
            }
        ]
    }
    parsed = _parse_media_metadata(meta, {"99"}, set())
    assert parsed.audio_streams[0]["selected"] is True
    assert parsed.audio_stream_index == 1


def test_parse_media_metadata_marks_stream_selected_by_flag() -> None:
    meta = {
        "Media": [
            {
                "Part": [
                    {
                        "file": "/f.mkv",
                        "Stream": [
                            {"streamType": 2, "id": "5", "index": 2, "displayTitle": "French", "selected": True}
                        ],
                    }
                ]
            }
        ]
    }
    parsed = _parse_media_metadata(meta, set(), set())
    assert parsed.audio_streams[0]["selected"] is True
    assert parsed.audio_stream_index == 2


def test_parse_media_metadata_label_falls_back_to_title() -> None:
    meta = {
        "Media": [
            {
                "Part": [
                    {
                        "file": "/f.mkv",
                        "Stream": [{"streamType": 2, "id": "1", "index": 1, "displayTitle": "", "title": "Alt"}],
                    }
                ]
            }
        ]
    }
    parsed = _parse_media_metadata(meta, set(), set())
    assert parsed.audio_streams[0]["label"] == "Alt"


def test_parse_media_metadata_label_falls_back_to_track_number() -> None:
    meta = {
        "Media": [
            {
                "Part": [
                    {
                        "file": "/f.mkv",
                        "Stream": [{"streamType": 2, "id": "1", "index": 3, "displayTitle": "", "title": ""}],
                    }
                ]
            }
        ]
    }
    parsed = _parse_media_metadata(meta, set(), set())
    assert parsed.audio_streams[0]["label"] == "Track 3"


def test_parse_media_metadata_audio_index_set_to_first_selected() -> None:
    meta = {
        "Media": [
            {
                "Part": [
                    {
                        "file": "/f.mkv",
                        "Stream": [
                            {"streamType": 2, "id": "1", "index": 1, "displayTitle": "A", "selected": True},
                            {"streamType": 2, "id": "2", "index": 2, "displayTitle": "B", "selected": True},
                        ],
                    }
                ]
            }
        ]
    }
    parsed = _parse_media_metadata(meta, set(), set())
    assert parsed.audio_stream_index == 1


def test_parse_media_metadata_subtitle_stream_parsed() -> None:
    meta = {
        "Media": [
            {
                "Part": [
                    {
                        "file": "/f.mkv",
                        "Stream": [
                            {
                                "streamType": 3,
                                "id": "77",
                                "index": 3,
                                "displayTitle": "English (SRT)",
                                "codec": "srt",
                                "selected": True,
                            }
                        ],
                    }
                ]
            }
        ]
    }
    parsed = _parse_media_metadata(meta, set(), {"77"})
    assert len(parsed.subtitle_streams) == 1
    sub = parsed.subtitle_streams[0]
    assert sub["index"] == 3
    assert sub["label"] == "English (SRT)"
    assert sub["codec"] == "srt"
    assert sub["burnable"] is True
    assert sub["selected"] is True
    assert parsed.subtitle_stream_index == 3


def test_parse_media_metadata_image_subtitle_not_burnable() -> None:
    meta = {
        "Media": [
            {
                "Part": [
                    {
                        "file": "/f.mkv",
                        "Stream": [
                            {
                                "streamType": 3,
                                "id": "88",
                                "index": 4,
                                "displayTitle": "English (PGS)",
                                "codec": "pgssub",
                                "selected": True,
                            }
                        ],
                    }
                ]
            }
        ]
    }
    parsed = _parse_media_metadata(meta, set(), {"88"})
    assert parsed.subtitle_streams[0]["burnable"] is False


def test_parse_media_metadata_subtitle_index_first_selected() -> None:
    meta = {
        "Media": [
            {
                "Part": [
                    {
                        "file": "/f.mkv",
                        "Stream": [
                            {
                                "streamType": 3,
                                "id": "1",
                                "index": 3,
                                "displayTitle": "A",
                                "codec": "srt",
                                "selected": True,
                            },
                            {
                                "streamType": 3,
                                "id": "2",
                                "index": 4,
                                "displayTitle": "B",
                                "codec": "srt",
                                "selected": True,
                            },
                        ],
                    }
                ]
            }
        ]
    }
    parsed = _parse_media_metadata(meta, set(), set())
    assert parsed.subtitle_stream_index == 3
