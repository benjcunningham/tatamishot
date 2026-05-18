from tatamishot.plex import _parse_media_metadata, _selected_audio_ids


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


def test_parse_media_metadata_empty() -> None:
    fp, streams, idx = _parse_media_metadata({}, set())
    assert fp is None
    assert streams == []
    assert idx is None


def test_parse_media_metadata_extracts_file_path() -> None:
    meta = {"Media": [{"Part": [{"file": "/media/movie.mkv", "Stream": []}]}]}
    fp, _, _ = _parse_media_metadata(meta, set())
    assert fp == "/media/movie.mkv"


def test_parse_media_metadata_skips_non_audio_streams() -> None:
    meta = {"Media": [{"Part": [{"file": "/f.mkv", "Stream": [{"streamType": 1, "id": "1", "index": 0}]}]}]}
    _, streams, _ = _parse_media_metadata(meta, set())
    assert streams == []


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
    _, streams, idx = _parse_media_metadata(meta, {"99"})
    assert streams[0]["selected"] is True
    assert idx == 1


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
    _, streams, idx = _parse_media_metadata(meta, set())
    assert streams[0]["selected"] is True
    assert idx == 2


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
    _, streams, _ = _parse_media_metadata(meta, set())
    assert streams[0]["label"] == "Alt"


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
    _, streams, _ = _parse_media_metadata(meta, set())
    assert streams[0]["label"] == "Track 3"


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
    _, _, idx = _parse_media_metadata(meta, set())
    assert idx == 1
