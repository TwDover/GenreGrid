# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""End-to-end tests through the real HTTP layer (FastAPI TestClient): the same
JSON/multipart contracts the frontend uses, exercised as full workflows —
build → re-roll → restore → mix → import. Complements the unit suites, which
call the Python functions directly."""
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.midi_writer import NoteEvent, write_midi

client = TestClient(app)


def _build_payload(**overrides):
    payload = {
        "style_id": "lofi", "key": "C", "scale": "major", "bpm": 90,
        "template": "compact", "parts": ["chords", "bass", "melody", "drums"],
        "seed": 71, "use_priors": False,
    }
    payload.update(overrides)
    return payload


@pytest.fixture(scope="module")
def song():
    r = client.post("/build-song", json=_build_payload())
    assert r.status_code == 200
    return r.json()


def test_generate_loop_over_http():
    r = client.post("/generate", json={
        "style_id": "lofi", "key": "C", "scale": "major", "bpm": 90, "bars": 4,
        "complexity": 0.5, "variation": 0.4, "parts": ["chords", "bass", "melody", "drums"],
        "mode": "loop", "seed": 3, "humanize": 0.5, "blend_amount": 0.5, "use_priors": False,
    })
    assert r.status_code == 200
    body = r.json()
    assert {f["part"] for f in body["files"]} >= {"chords", "bass", "melody", "drums"}
    # Stems are actually downloadable
    stem = client.get(body["files"][0]["url"])
    assert stem.status_code == 200 and stem.content[:4] == b"MThd"


def test_cors_allows_localhost_but_not_external_sites():
    # A random-port renderer origin (as in the packaged app) is granted
    r = client.options("/generate", headers={
        "Origin": "http://127.0.0.1:53311", "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") == "http://127.0.0.1:53311"

    # An arbitrary website the user might visit is NOT granted access
    r = client.options("/generate", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") is None


def test_export_download_rejects_path_traversal():
    # A generation whose stems are genuinely downloadable
    r = client.post("/generate", json={
        "style_id": "lofi", "key": "C", "scale": "major", "bpm": 90, "bars": 4,
        "parts": ["chords"], "mode": "loop", "seed": 9, "use_priors": False,
    })
    assert r.status_code == 200
    gid = r.json()["generation_id"]

    # A real stem still downloads (regression guard for the hardened route)
    assert client.get(f"/exports/{gid}/chords.mid").status_code == 200

    # Encoded traversal in the filename must not escape the generation dir
    for evil in ("..%2f..%2fmeta.json", "..%2F..%2F..%2Fetc%2Fpasswd", "%2e%2e%2fchords.mid"):
        resp = client.get(f"/exports/{gid}/{evil}")
        assert resp.status_code in (404, 422), evil
        assert b"root:" not in resp.content

    # A malformed generation id is rejected before any filesystem access
    assert client.get("/exports/..%2f..%2fetc/passwd").status_code in (404, 422)


def test_song_lifecycle_over_http(song):
    gid = song["generation_id"]
    assert song["sections"][-1]["section_type"] == "ending"
    assert all(s["quality"] is not None for s in song["sections"][:-1])

    # Re-roll one section; the response covers every rewritten stem
    r = client.post("/regenerate-song-section", json={"generation_id": gid, "section_index": 1})
    assert r.status_code == 200
    assert {f["part"] for f in r.json()} >= {"melody", "song"}

    # That mutation created a restorable version
    versions = client.get(f"/song-versions/{gid}").json()
    assert len(versions) == 1
    r = client.post("/restore-song-version", json={"generation_id": gid, "version_id": versions[0]["id"]})
    assert r.status_code == 200

    # Re-roll a single part, then undo it
    r = client.post("/regenerate-song-part", json={"generation_id": gid, "part": "drums"})
    assert r.status_code == 200 and r.json()["part"] == "drums"
    r = client.post("/undo-song-part", json={"generation_id": gid, "part": "drums"})
    assert r.status_code == 200

    # Add a part that wasn't in the build
    r = client.post("/regenerate-song-part", json={"generation_id": gid, "part": "pads"})
    assert r.status_code == 200 and r.json()["part"] == "pads"

    # The song shows up in the recent-songs listing with its files
    songs = client.get("/songs").json()
    entry = next(s for s in songs if s["generation_id"] == gid)
    assert {f["part"] for f in entry["files"]} >= {"pads", "song"}


def test_mixer_over_http(song):
    gid = song["generation_id"]
    r = client.post("/set-part-gain", json={"generation_id": gid, "part": "bass", "gain": 0.5})
    assert r.status_code == 200

    # Gain persists and is surfaced by /songs
    songs = client.get("/songs").json()
    entry = next(s for s in songs if s["generation_id"] == gid)
    assert entry["mixer"] == {"bass": 0.5}

    # Setting back to 1.0 restores the generated balance (absolute, not cumulative)
    r = client.post("/set-part-gain", json={"generation_id": gid, "part": "bass", "gain": 1.0})
    assert r.status_code == 200

    # Unknown stem is a clean 404, not a crash
    r = client.post("/set-part-gain", json={"generation_id": gid, "part": "kazoo", "gain": 1.0})
    assert r.status_code == 404


def test_melody_import_over_http():
    # A simple diatonic melody, uploaded as real multipart form data
    sc = [0, 2, 4, 5, 7, 9, 11]
    ev = [NoteEvent(60 + sc[s], bar * 4 + q, 0.9, 90, 0)
          for bar, steps in enumerate([[0, 2, 4, 2], [0, 3, 5, 3], [4, 2, 1, 0], [0, 1, 2, 0]])
          for q, s in enumerate(steps)]
    import tempfile
    import os
    fd, path = tempfile.mkstemp(suffix=".mid")
    os.close(fd)
    write_midi(ev, path, bpm=100)
    data = open(path, "rb").read()
    os.unlink(path)

    r = client.post("/build-song-from-melody",
                    files={"file": ("hook.mid", io.BytesIO(data), "audio/midi")},
                    data={"style_id": "lofi", "template": "compact",
                          "parts": "chords,bass,melody,drums", "seed": "72",
                          "use_priors": "false", "final_chorus_lift": "0"})
    assert r.status_code == 200
    body = r.json()
    assert body["key"].startswith("C major")   # detected, not defaulted

    # Garbage upload is a clean 400
    r = client.post("/build-song-from-melody",
                    files={"file": ("junk.mid", io.BytesIO(b"not midi"), "audio/midi")},
                    data={"style_id": "lofi"})
    assert r.status_code == 400
