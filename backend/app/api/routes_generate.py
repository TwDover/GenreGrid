import random
import uuid
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.models.schemas import GenerateRequest, GenerateResponse, FileInfo, GenerateSummary
from app.services.style_loader import load_style
from app.services.midi_writer import NoteEvent, write_midi, write_combined_midi
from app.generators.chords import generate_chords
from app.generators.bass import generate_bass
from app.generators.melody import generate_melody
from app.generators.drums import generate_drums
from app.generators.arpeggio import generate_arpeggio
from app.core.config import EXPORTS_DIR

router = APIRouter()


_VELOCITY_DROP = 20  # notes quieter than this are inaudible — discard them


def _drop_quiet(events: list[NoteEvent]) -> list[NoteEvent]:
    return [e for e in events if e.velocity >= _VELOCITY_DROP]


def _shift(events: list[NoteEvent], beats: float) -> list[NoteEvent]:
    return [
        NoteEvent(pitch=e.pitch, start=e.start + beats, duration=e.duration,
                  velocity=e.velocity, channel=e.channel)
        for e in events
    ]


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

    # A/B structure for tracks >= 8 bars: sparse first half → full second half
    use_sections = req.bars >= 8
    half = req.bars // 2 if use_sections else req.bars
    b_offset = half * 4.0  # beats

    def _make_generators(bars: int, complexity: float, include_arpeggio: bool) -> dict:
        g = {
            "chords":   lambda b=bars, c=complexity: generate_chords(style, req.key, req.scale, b, c, req.variation, progression),
            "bass":     lambda b=bars, c=complexity: generate_bass(style, req.key, req.scale, b, c, req.variation, progression),
            "melody":   lambda b=bars, c=complexity: generate_melody(style, req.key, req.scale, b, c, req.variation, progression),
            "drums":    lambda b=bars: generate_drums(style, b, req.complexity, req.variation),
        }
        if include_arpeggio:
            g["arpeggio"] = lambda b=bars, c=complexity: generate_arpeggio(style, req.key, req.scale, b, c, req.variation, progression)
        return g

    all_events: dict[str, list[NoteEvent]] = {}

    if use_sections:
        a_complexity = req.complexity * 0.55
        gen_a = _make_generators(half, a_complexity, include_arpeggio=False)
        gen_b = _make_generators(half, req.complexity, include_arpeggio=True)

        for part in req.parts:
            a_fn = gen_a.get(part)
            b_fn = gen_b.get(part)
            a_evts = a_fn() if a_fn else []
            b_evts = _shift(b_fn(), b_offset) if b_fn else []
            if a_evts or b_evts:
                all_events[part] = a_evts + b_evts
    else:
        gen = _make_generators(req.bars, req.complexity, include_arpeggio=True)
        for part in req.parts:
            fn = gen.get(part)
            if fn:
                all_events[part] = fn()

    files = []
    for part, events in all_events.items():
        events = _drop_quiet(events)
        filename = f"{part}.mid"
        out_path = output_dir / filename
        write_midi(events, out_path, bpm=bpm)
        files.append(FileInfo(part=part, filename=filename, url=f"/exports/{gen_id}/{filename}"))

    # Combined export
    if len(all_events) > 1:
        combined_path = output_dir / "combined.mid"
        clean_events = {p: _drop_quiet(e) for p, e in all_events.items()}
        write_combined_midi(clean_events, combined_path, bpm=bpm)
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
