# GenreGrid — a style-based MIDI generator.
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Recorded audio clips (roadmap 9.4): save/delete persistence, .ggproj
round-trip, and the byte-identical invariant for untouched songs."""
import asyncio
import io
import json
import wave
import zipfile

import pytest
from fastapi import HTTPException, UploadFile

from app.api.routes_song import (build_song, save_audio_clip, delete_audio_clip,
                                 export_project, import_project)
from app.core.config import EXPORTS_DIR
from app.models.schemas import BuildSongRequest


def _song(seed=61, **kw):
    args = dict(style_id="lofi", key="C", scale="major", bpm=90, template="compact",
                parts=["chords", "bass", "melody", "drums"], seed=seed, use_priors=False)
    args.update(kw)
    return build_song(BuildSongRequest(**args))


def _wav_bytes(seconds=0.5, rate=44100) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


def _save(gen_id, start_bar=0, bars=4, data=None):
    return asyncio.run(save_audio_clip(
        generation_id=gen_id, start_bar=start_bar, bars=bars,
        file=UploadFile(filename="clip.wav", file=io.BytesIO(data or _wav_bytes())),
    ))


def test_save_audio_clip_persists_file_and_meta():
    r = _song(seed=1)
    info = _save(r.generation_id, start_bar=8, bars=4)
    assert info.part == "audio"
    assert info.start_bar == 8 and info.bars == 4
    assert info.url == f"/exports/{r.generation_id}/audio_clip.wav"

    d = EXPORTS_DIR / r.generation_id
    assert (d / "audio_clip.wav").exists()
    meta = json.loads((d / "song_meta.json").read_text())
    assert meta["audio_clip"] == {"filename": "audio_clip.wav", "start_bar": 8, "bars": 4}


def test_re_recording_replaces_the_previous_take():
    r = _song(seed=2)
    _save(r.generation_id, start_bar=0, bars=4, data=_wav_bytes(0.3))
    first_bytes = (EXPORTS_DIR / r.generation_id / "audio_clip.wav").read_bytes()
    info = _save(r.generation_id, start_bar=4, bars=8, data=_wav_bytes(0.9))
    second_bytes = (EXPORTS_DIR / r.generation_id / "audio_clip.wav").read_bytes()
    assert second_bytes != first_bytes
    assert info.start_bar == 4 and info.bars == 8
    meta = json.loads((EXPORTS_DIR / r.generation_id / "song_meta.json").read_text())
    assert meta["audio_clip"]["start_bar"] == 4   # not a stale merge of both saves


def test_save_audio_clip_snapshots_history():
    r = _song(seed=3)
    d = EXPORTS_DIR / r.generation_id
    _save(r.generation_id)
    versions = list((d / "versions").iterdir())
    assert len(versions) == 1   # pre-mutation state snapshotted


def test_save_audio_clip_rejects_non_wav():
    r = _song(seed=4)
    with pytest.raises(HTTPException):
        _save(r.generation_id, data=b"not a wav file at all")


def test_save_audio_clip_404_on_unknown_generation():
    with pytest.raises(HTTPException):
        _save("does-not-exist-anywhere")


def test_delete_audio_clip_removes_file_and_meta():
    r = _song(seed=5)
    _save(r.generation_id)
    d = EXPORTS_DIR / r.generation_id
    result = delete_audio_clip(r.generation_id)
    assert result["deleted"] is True
    assert not (d / "audio_clip.wav").exists()
    meta = json.loads((d / "song_meta.json").read_text())
    assert "audio_clip" not in meta


def test_delete_audio_clip_404_when_none_exists():
    r = _song(seed=6)
    with pytest.raises(HTTPException):
        delete_audio_clip(r.generation_id)


def test_song_without_a_clip_has_no_audio_clip_key():
    """Byte-identical invariant: a song nobody recorded into stays untouched —
    no `audio_clip` key appears from mere generation."""
    r = _song(seed=7)
    assert r.audio_clip is None
    meta = json.loads((EXPORTS_DIR / r.generation_id / "song_meta.json").read_text())
    assert "audio_clip" not in meta


def _collect_streaming(resp):
    """Drain a StreamingResponse body into bytes (sync test helper)."""
    async def run():
        chunks = []
        async for c in resp.body_iterator:
            chunks.append(c if isinstance(c, (bytes, bytearray)) else c.encode())
        return b"".join(chunks)
    return asyncio.run(run())


def test_ggproj_round_trips_the_audio_clip():
    r = _song(seed=8)
    _save(r.generation_id, start_bar=0, bars=4, data=_wav_bytes(0.4))
    clip_bytes = (EXPORTS_DIR / r.generation_id / "audio_clip.wav").read_bytes()

    zip_bytes = _collect_streaming(export_project(r.generation_id))
    names = set(zipfile.ZipFile(io.BytesIO(zip_bytes)).namelist())
    assert "audio_clip.wav" in names

    imported = asyncio.run(import_project(UploadFile(filename="p.ggproj", file=io.BytesIO(zip_bytes))))
    nd = EXPORTS_DIR / imported.generation_id
    assert (nd / "audio_clip.wav").read_bytes() == clip_bytes
    assert imported.audio_clip is not None
    assert imported.audio_clip.start_bar == 0 and imported.audio_clip.bars == 4
