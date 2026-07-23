# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.library import save_generation, list_library, exclude_generation
from app.core.config import EXPORTS_DIR

router = APIRouter(prefix="/library", tags=["library"])

# How much more a user-kept generation counts than a merely high-scoring one.
_KEEP_WEIGHT = 2.5


def record_export_keep(gen_id: str) -> bool:
    """Count a download/export as an implicit positive: keep the generation in
    the library with extra weight, learning from what the user actually takes.
    Best-effort — needs the meta.json + patterns.json written at gen time."""
    import json
    export_dir = EXPORTS_DIR / gen_id
    meta_file, pat_file = export_dir / "meta.json", export_dir / "patterns.json"
    if not (meta_file.exists() and pat_file.exists()):
        return False
    try:
        meta = json.loads(meta_file.read_text())
        patterns = json.loads(pat_file.read_text())
        save_generation(
            gen_id=gen_id, style_id=meta["style_id"], key=meta["key"],
            scale=meta["scale"], bpm=meta["bpm"], bars=meta["bars"],
            seed=meta["seed"], quality_raw=meta.get("quality", {}),
            patterns=patterns, keep=_KEEP_WEIGHT, source="export",
        )
        return True
    except Exception:
        return False


class FeedbackRequest(BaseModel):
    gen_id: str
    style_id: str
    vote: str          # "up" | "down"


@router.post("/feedback")
def feedback(req: FeedbackRequest):
    """Thumbs up/down on the quality badge (roadmap-2 item 9). Up saves the
    generation regardless of score, weighted so it steers the learner toward the
    user's taste; down excludes that generation's patterns from the library."""
    if req.vote == "down":
        removed = exclude_generation(req.style_id, req.gen_id)
        return {"gen_id": req.gen_id, "vote": "down", "excluded": removed}
    if req.vote != "up":
        raise HTTPException(status_code=400, detail="vote must be 'up' or 'down'")

    import json
    export_dir = EXPORTS_DIR / req.gen_id
    pat_file = export_dir / "patterns.json"
    if not pat_file.exists():
        raise HTTPException(status_code=404, detail="Pattern data not found for this generation")
    patterns = json.loads(pat_file.read_text())
    meta_file = export_dir / "meta.json"
    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    save_generation(
        gen_id=req.gen_id, style_id=req.style_id,
        key=meta.get("key", "C"), scale=meta.get("scale", "minor"),
        bpm=meta.get("bpm", 120), bars=meta.get("bars", 8), seed=meta.get("seed", 0),
        quality_raw=meta.get("quality", {}), patterns=patterns,
        keep=_KEEP_WEIGHT, source="thumbs_up",
    )
    return {"gen_id": req.gen_id, "vote": "up", "saved": True}


class SaveRequest(BaseModel):
    gen_id: str
    style_id: str
    key: str
    scale: str
    bpm: int
    bars: int
    seed: int
    quality: dict


@router.post("/save")
def save(req: SaveRequest):
    """Manually save a generation to the library.

    Reads the pre-computed patterns.json written alongside the MIDI files
    at generation time, so no MIDI parsing is needed here.
    """
    export_dir = EXPORTS_DIR / req.gen_id
    patterns_file = export_dir / "patterns.json"

    if not export_dir.exists():
        raise HTTPException(status_code=404, detail="Generation not found")
    if not patterns_file.exists():
        raise HTTPException(status_code=404, detail="Pattern data not found for this generation")

    import json
    patterns = json.loads(patterns_file.read_text())

    save_generation(
        gen_id=req.gen_id,
        style_id=req.style_id,
        key=req.key,
        scale=req.scale,
        bpm=req.bpm,
        bars=req.bars,
        seed=req.seed,
        quality_raw=req.quality,
        patterns=patterns,
    )
    return {"saved": True, "gen_id": req.gen_id}


@router.get("/")
def list_all():
    """List all saved library entries, newest first."""
    return list_library()


@router.get("/counts")
def get_counts():
    """Return a dict of style_id -> saved entry count."""
    from app.services.library import LIBRARY_DIR
    counts = {}
    if LIBRARY_DIR.exists():
        for d in LIBRARY_DIR.iterdir():
            if d.is_dir():
                counts[d.name] = len(list(d.glob("*.json")))
    return counts


@router.get("/{style_id}")
def list_by_style(style_id: str):
    """List saved entries for a specific style."""
    return list_library(style_id)
