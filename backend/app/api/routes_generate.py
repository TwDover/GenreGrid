import random
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.models.schemas import GenerateRequest, GenerateResponse, FileInfo, GenerateSummary
from app.services.style_loader import load_style
from app.services.midi_writer import write_midi, write_combined_midi
from app.generators.chords import generate_chords
from app.generators.bass import generate_bass
from app.generators.melody import generate_melody
from app.generators.drums import generate_drums
from app.core.config import EXPORTS_DIR

router = APIRouter()


@router.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    try:
        style = load_style(req.style_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Seed random for reproducibility
    seed = req.seed if req.seed is not None else random.randint(0, 2**31 - 1)
    random.seed(seed)

    # Clamp BPM to the style's suggested range
    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = max(bpm_min, min(bpm_max, req.bpm))

    gen_id = str(uuid.uuid4())[:8]
    output_dir = EXPORTS_DIR / gen_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Pick one progression shared across chords, bass, and melody
    templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
    progression = random.choice(templates)

    part_generators = {
        "chords": lambda: generate_chords(style, req.key, req.scale, req.bars, req.complexity, req.variation, progression),
        "bass":   lambda: generate_bass(style, req.key, req.scale, req.bars, req.complexity, req.variation, progression),
        "melody": lambda: generate_melody(style, req.key, req.scale, req.bars, req.complexity, req.variation, progression),
        "drums":  lambda: generate_drums(style, req.bars, req.complexity, req.variation),
    }

    files = []
    all_events = {}

    for part in req.parts:
        generator = part_generators.get(part)
        if generator is None:
            continue
        events = generator()
        all_events[part] = events
        filename = f"{part}.mid"
        out_path = output_dir / filename
        write_midi(events, out_path, bpm=bpm)
        files.append(FileInfo(part=part, filename=filename, url=f"/exports/{gen_id}/{filename}"))

    # Combined export
    if len(all_events) > 1:
        combined_path = output_dir / "combined.mid"
        write_combined_midi(all_events, combined_path, bpm=bpm)
        files.append(FileInfo(part="combined", filename="combined.mid", url=f"/exports/{gen_id}/combined.mid"))

    return GenerateResponse(
        generation_id=gen_id,
        style=req.style_id,
        files=files,
        summary=GenerateSummary(key=f"{req.key} {req.scale}", key_root=req.key, scale=req.scale, bpm=bpm, bars=req.bars),
        seed=seed,
    )


@router.get("/exports/{gen_id}/{filename}")
def download_export(gen_id: str, filename: str):
    file_path = EXPORTS_DIR / gen_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path), media_type="audio/midi", filename=filename)
