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

PART_GENERATORS = {
    "chords": lambda style, req: generate_chords(style, req.key, req.scale, req.bars, req.complexity, req.variation),
    "bass":   lambda style, req: generate_bass(style, req.key, req.scale, req.bars, req.complexity, req.variation),
    "melody": lambda style, req: generate_melody(style, req.key, req.scale, req.bars, req.complexity, req.variation),
    "drums":  lambda style, req: generate_drums(style, req.bars, req.complexity, req.variation),
}


@router.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    try:
        style = load_style(req.style_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    gen_id = str(uuid.uuid4())[:8]
    output_dir = EXPORTS_DIR / gen_id
    output_dir.mkdir(parents=True, exist_ok=True)

    files = []
    all_events = {}

    for part in req.parts:
        generator = PART_GENERATORS.get(part)
        if generator is None:
            continue
        events = generator(style, req)
        all_events[part] = events
        filename = f"{part}.mid"
        out_path = output_dir / filename
        write_midi(events, out_path, bpm=req.bpm)
        files.append(FileInfo(part=part, filename=filename, url=f"/exports/{gen_id}/{filename}"))

    # Combined export
    if len(all_events) > 1:
        combined_path = output_dir / "combined.mid"
        write_combined_midi(all_events, combined_path, bpm=req.bpm)
        files.append(FileInfo(part="combined", filename="combined.mid", url=f"/exports/{gen_id}/combined.mid"))

    return GenerateResponse(
        generation_id=gen_id,
        style=req.style_id,
        files=files,
        summary=GenerateSummary(key=f"{req.key} {req.scale}", bpm=req.bpm, bars=req.bars),
    )


@router.get("/exports/{gen_id}/{filename}")
def download_export(gen_id: str, filename: str):
    file_path = EXPORTS_DIR / gen_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path), media_type="audio/midi", filename=filename)
