# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
import io
import random
import re
import tempfile
import os
from functools import lru_cache

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from app.services.style_loader import list_styles, get_style_detail, save_custom_style, load_style
from app.models.schemas import StyleInfo

router = APIRouter()

_VALID_ID = re.compile(r'^[a-z0-9_]{1,40}$')


@router.get("/styles", response_model=list[StyleInfo])
def get_styles():
    return list_styles()


@router.get("/styles/{style_id}/detail")
def get_style_detail_route(style_id: str):
    try:
        return get_style_detail(style_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Style not found: {style_id}")


@router.get("/styles/{style_id}/preview")
def style_preview(style_id: str):
    """Return a short 4-bar MIDI demo for a style, generated with a fixed seed."""
    if not _VALID_ID.match(style_id):
        raise HTTPException(status_code=422, detail="Invalid style id")
    try:
        midi_bytes = _build_preview(style_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Preview generation failed")
    return Response(content=midi_bytes, media_type="audio/midi",
                    headers={"Cache-Control": "public, max-age=3600"})


@lru_cache(maxsize=64)
def _build_preview(style_id: str) -> bytes:
    from app.generators.chords import generate_chords, resolve_progression
    from app.generators.bass import generate_bass
    from app.generators.melody import generate_melody
    from app.generators.drums import generate_drums
    from app.services.midi_writer import write_combined_midi

    style = load_style(style_id)
    bpm_range = style.get("bpm_range", [120, 140])
    bpm = (bpm_range[0] + bpm_range[1]) // 2
    scale = style.get("default_scale", "minor")
    key = "C"
    bars = 4
    complexity = 0.5
    variation = 0.4

    style = {**style, "_humanize_scale": 0.4}

    random.seed(42)
    templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
    progression = templates[0] if templates else ["i", "VI", "III", "VII"]
    resolved = resolve_progression(progression, scale, complexity)

    drum_evts = generate_drums(style, bars, complexity, variation)
    kick_times = [e.start for e in drum_evts if e.pitch == 36]
    chord_evts = generate_chords(style, key, scale, bars, complexity, variation, progression, resolved)
    bass_evts = generate_bass(style, key, scale, bars, complexity, variation, progression, kick_times)
    melody_evts = generate_melody(style, key, scale, bars, complexity, variation, resolved)

    parts = {"chords": chord_evts, "bass": bass_evts, "melody": melody_evts, "drums": drum_evts}

    fd, tmp = tempfile.mkstemp(suffix=".mid")
    os.close(fd)
    try:
        write_combined_midi(parts, tmp, bpm=bpm)
        with open(tmp, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp)


@router.post("/styles/custom")
def create_custom_style(body: dict):
    style_id = body.get("id", "")
    if not _VALID_ID.match(style_id):
        raise HTTPException(status_code=422, detail="Style id must be 1-40 lowercase alphanumeric/underscore chars")
    if not body.get("name"):
        raise HTTPException(status_code=422, detail="Style name is required")
    required = ("bpm_range", "default_scale", "progression_templates")
    for field in required:
        if field not in body:
            raise HTTPException(status_code=422, detail=f"Missing required field: {field}")
    return save_custom_style(body)
