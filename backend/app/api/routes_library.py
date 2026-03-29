from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.library import save_generation, is_saved, list_library
from app.core.config import EXPORTS_DIR

router = APIRouter(prefix="/library", tags=["library"])


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
