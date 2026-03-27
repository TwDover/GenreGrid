import random
import secrets
import uuid
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.models.schemas import GenerateRequest, RegeneratePartRequest, GenerateResponse, FileInfo, GenerateSummary
from app.services.style_loader import load_style
from app.services.midi_writer import NoteEvent, write_midi, write_combined_midi, rebuild_combined_from_parts
from app.generators.chords import generate_chords, resolve_progression
from app.generators.bass import generate_bass
from app.generators.melody import generate_melody
from app.generators.drums import generate_drums
from app.generators.arpeggio import generate_arpeggio
from app.core.config import EXPORTS_DIR
from app.core.constants import DRUM_MAP

router = APIRouter()

# General MIDI program numbers per part, keyed by style_id.
# Parts not listed fall back to _DEFAULT_PROGRAMS.
# GM reference: 0=Piano, 5=Rhodes, 25=Steel Guitar, 32=Acoustic Bass, 33=Elec Bass,
#   38=Synth Bass, 43=Contrabass, 44=Tremolo Strings, 48=Strings, 56=Trumpet,
#   65=Alto Sax, 66=Tenor Sax, 68=Oboe, 73=Flute, 80=Lead Square, 81=Lead Saw,
#   88=Pad New Age, 89=Pad Warm, 90=Pad PolySync, 91=Pad Choir, 92=Pad Bowed
_DEFAULT_PROGRAMS: dict[str, int] = {
    "chords":   0,   # Acoustic Grand Piano
    "bass":     33,  # Electric Bass (finger)
    "melody":   0,   # Acoustic Grand Piano
    "arpeggio": 0,   # Acoustic Grand Piano
}
_STYLE_PROGRAMS: dict[str, dict[str, int]] = {
    # Jazz / Soul / Funk
    "jazz":            {"bass": 32, "melody": 65},
    "latin_jazz":      {"bass": 32, "melody": 65},
    "bossa_nova":      {"chords": 25, "bass": 32, "melody": 73, "arpeggio": 25},
    "soul":            {"chords": 5,  "bass": 33, "melody": 66, "arpeggio": 5},
    "rnb":             {"chords": 5,  "bass": 33, "arpeggio": 5},
    "funk":            {"chords": 5,  "bass": 33, "melody": 65, "arpeggio": 5},
    "lofi":            {"bass": 33},
    # Electronic / Dance
    "synthwave":       {"chords": 90, "bass": 38, "melody": 81, "arpeggio": 80},
    "house":           {"chords": 90, "bass": 38, "melody": 81, "arpeggio": 80},
    "techno":          {"chords": 91, "bass": 38, "melody": 80, "arpeggio": 80},
    "drum_and_bass":   {"chords": 90, "bass": 38, "melody": 81, "arpeggio": 80},
    "future_bass":     {"chords": 90, "bass": 38, "melody": 81, "arpeggio": 80},
    "jersey_club":     {"bass": 38},
    "dancehall":       {"bass": 38},
    "reggaeton":       {"bass": 38},
    # Hip-hop / Trap
    "trap_soul":       {"chords": 88, "bass": 38, "arpeggio": 88},
    "dark_trap":       {"chords": 88, "bass": 38, "melody": 80, "arpeggio": 80},
    "cloud_rap":       {"chords": 88, "bass": 38, "arpeggio": 88},
    "drill":           {"bass": 38},
    "boom_bap":        {"bass": 33},
    # Cinematic / Ambient
    "cinematic":       {"chords": 48, "bass": 43, "melody": 56, "arpeggio": 44},
    "epic_orchestral": {"chords": 48, "bass": 43, "melody": 56, "arpeggio": 44},
    "ambient":         {"chords": 89, "bass": 38, "melody": 73, "arpeggio": 88},
    "dark_ambient":    {"chords": 92, "bass": 38, "melody": 68, "arpeggio": 92},
    # Afro / Latin
    "afrobeats":       {"bass": 33},
    "cumbia":          {"bass": 33},
}

_VELOCITY_DROP = 20  # notes quieter than this are inaudible — discard them

# Per-part velocity scale factors. Bass sits loudest, chords slightly back,
# melody present above chords, arpeggio light. Drums are not scaled.
_VELOCITY_SCALE: dict[str, float] = {
    "bass":     1.00,
    "chords":   0.80,
    "melody":   0.90,
    "arpeggio": 0.72,
}


def _drop_quiet(events: list[NoteEvent]) -> list[NoteEvent]:
    return [e for e in events if e.velocity >= _VELOCITY_DROP]


def _scale_velocity(events: list[NoteEvent], part: str) -> list[NoteEvent]:
    factor = _VELOCITY_SCALE.get(part, 1.0)
    if factor == 1.0:
        return events
    return [
        NoteEvent(pitch=e.pitch, start=e.start, duration=e.duration,
                  velocity=max(1, min(127, int(e.velocity * factor))),
                  channel=e.channel)
        for e in events
    ]


def _shift(events: list[NoteEvent], beats: float) -> list[NoteEvent]:
    return [
        NoteEvent(pitch=e.pitch, start=e.start + beats, duration=e.duration,
                  velocity=e.velocity, channel=e.channel)
        for e in events
    ]


def _prevent_parallel_motion(
    melody_events: list[NoteEvent],
    bass_events: list[NoteEvent],
    scale_notes: list[int] | None = None,
) -> list[NoteEvent]:
    """Nudge melody notes that form parallel octaves or fifths with the bass.

    Only fixes the worst offender (direct parallel motion into an octave or fifth)
    by raising or lowering by 1 semitone. Preserves all timing and velocity.
    Parallel motion into a unison (octave) is most objectionable; fifths are secondary.
    """
    if not bass_events or not melody_events:
        return melody_events

    # Build a quick lookup: for each beat position, what bass pitch is sounding?
    bass_sorted = sorted(bass_events, key=lambda e: e.start)

    def _bass_pitch_at(beat: float) -> int | None:
        # Find the last bass note that started at or before `beat`
        result = None
        for e in bass_sorted:
            if e.start <= beat + 0.05:
                result = e.pitch
            else:
                break
        return result

    _PARALLEL_INTERVALS = {0, 7}   # unison/octave (mod 12) and fifth

    fixed = []
    for i, mel in enumerate(melody_events):
        b_pitch = _bass_pitch_at(mel.start)
        if b_pitch is None:
            fixed.append(mel)
            continue

        # Check current interval
        interval = (mel.pitch - b_pitch) % 12
        if interval not in _PARALLEL_INTERVALS:
            fixed.append(mel)
            continue

        # Check if the previous mel note also made the same interval with prev bass
        # (that's what makes it "parallel" — motion into the same interval type)
        if i > 0:
            prev_mel = melody_events[i - 1]
            prev_bass = _bass_pitch_at(prev_mel.start)
            if prev_bass is not None:
                prev_interval = (prev_mel.pitch - prev_bass) % 12
                if prev_interval in _PARALLEL_INTERVALS:
                    # Parallel motion confirmed — nudge melody ±1 semitone
                    new_pitch = mel.pitch + (1 if interval == 7 else 2)
                    new_pitch = max(48, min(96, new_pitch))
                    fixed.append(NoteEvent(
                        pitch=new_pitch, start=mel.start,
                        duration=mel.duration, velocity=mel.velocity, channel=mel.channel,
                    ))
                    continue

        fixed.append(mel)

    return fixed


def _plan_sections(total_bars: int, complexity: float, requested_parts: list[str]) -> list[dict]:
    """Return an arrangement arc as a list of section dicts.

    Each dict has: bars, complexity, parts, offset (in beats).
    Sections progress from sparse (foundation only) → full arrangement → sparse outro,
    so the output feels like a song with an energy curve rather than a looping pattern.
    """
    full   = list(requested_parts)
    no_arp = [p for p in requested_parts if p != "arpeggio"]
    sparse = [p for p in requested_parts if p in ("drums", "bass", "chords")]
    found  = [p for p in requested_parts if p in ("drums", "bass")]

    def sec(b: int, c_mul: float, p: list, off: int) -> dict:
        return {"bars": b, "complexity": max(0.1, complexity * c_mul), "parts": p, "offset": off}

    if total_bars <= 4:
        return [sec(total_bars, 1.0, full, 0)]

    if total_bars <= 8:
        intro = max(1, total_bars // 4)
        return [
            sec(intro,              0.35, found, 0),
            sec(total_bars - intro, 1.0,  full,  intro * 4),
        ]

    if total_bars <= 16:
        intro  = max(1, total_bars // 6)
        outro  = intro
        mid    = total_bars - intro - outro
        verse  = mid // 2
        chorus = mid - verse
        secs, off = [], 0
        secs.append(sec(intro,  0.3,  found,  off)); off += intro  * 4
        secs.append(sec(verse,  0.65, sparse, off)); off += verse  * 4
        secs.append(sec(chorus, 1.0,  full,   off)); off += chorus * 4
        secs.append(sec(outro,  0.35, found,  off))
        return secs

    # 17+ bars: full song arc — intro, verse, chorus, outro
    intro  = 2
    outro  = 2
    mid    = total_bars - intro - outro
    verse  = mid // 3
    chorus = mid - verse
    secs, off = [], 0
    secs.append(sec(intro,  0.25, found,  off)); off += intro  * 4
    secs.append(sec(verse,  0.6,  no_arp, off)); off += verse  * 4
    secs.append(sec(chorus, 1.0,  full,   off)); off += chorus * 4
    secs.append(sec(outro,  0.3,  found,  off))
    return secs


def _section_end_bars(sections: list[dict], current_section_offset: int) -> list[int]:
    """Return bar indices (relative to current section) that are section boundaries.

    Used to tell the drum generator where to place builds/fills at section transitions.
    """
    end_bars = []
    for sec in sections:
        sec_end_beat = sec["offset"] + sec["bars"] * 4
        # Convert to bar index within the current section
        bar_idx = (sec_end_beat - current_section_offset) // 4 - 1
        if 0 <= bar_idx:
            end_bars.append(int(bar_idx))
    return end_bars


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

    # Build GM instrument map: defaults merged with any style-specific overrides
    programs: dict[str, int] = {**_DEFAULT_PROGRAMS, **_STYLE_PROGRAMS.get(req.style_id, {})}

    # Pick one progression shared across chords, bass, and melody
    templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
    progression = random.choice(templates)
    hrb = style.get("harmonic_rhythm_bars", 1)
    if hrb > 1:
        progression = [chord for chord in progression for _ in range(hrb)]

    secondary_dominants = style.get("secondary_dominants", False)

    if req.mode == "loop":
        sections = [{"bars": req.bars, "complexity": req.complexity, "parts": req.parts, "offset": 0}]
    else:
        sections = _plan_sections(req.bars, req.complexity, req.parts)
    all_events: dict[str, list[NoteEvent]] = {part: [] for part in req.parts}

    for section in sections:
        s_bars  = section["bars"]
        s_cplx  = section["complexity"]
        s_parts = set(section["parts"])
        s_off   = section["offset"]

        # Pre-resolve chord substitutions once per section so chords and melody
        # target exactly the same chord tones (no secret substitutions).
        s_resolved = resolve_progression(progression, req.scale, s_cplx, secondary_dominants)

        # ── Step 1: Drums first — extract kick times for bass/velocity sync ──
        kick_times: list[float] = []
        if "drums" in req.parts and "drums" in s_parts:
            drum_evts = generate_drums(style, s_bars, s_cplx, req.variation,
                                       section_end_bars=_section_end_bars(sections, s_off))
            all_events["drums"].extend(_shift(drum_evts, s_off))
            kick_times = [e.start for e in drum_evts if e.pitch == DRUM_MAP["kick"]]

        # ── Step 2: All other parts with shared coordination data ─────────────
        has_melody = "melody" in s_parts
        for part in req.parts:
            if part not in s_parts or part == "drums":
                continue
            if part == "chords":
                evts = generate_chords(style, req.key, req.scale, s_bars, s_cplx,
                                       req.variation, progression, s_resolved)
            elif part == "bass":
                evts = generate_bass(style, req.key, req.scale, s_bars, s_cplx,
                                     req.variation, progression, kick_times)
            elif part == "melody":
                # melody receives the resolved progression so it targets the
                # same chord tones that chords.py is actually playing
                evts = generate_melody(style, req.key, req.scale, s_bars, s_cplx,
                                       req.variation, s_resolved)
            elif part == "arpeggio":
                # Push arpeggio one octave higher when melody is present to avoid
                # occupying the same register
                arp_octave = 6 if has_melody else 5
                evts = generate_arpeggio(style, req.key, req.scale, s_bars, s_cplx,
                                         req.variation, s_resolved, arp_octave)
            else:
                continue
            all_events[part].extend(_shift(evts, s_off))

    # Post-process: reduce parallel octaves/fifths between melody and bass
    if "melody" in all_events and "bass" in all_events:
        all_events["melody"] = _prevent_parallel_motion(
            all_events["melody"], all_events["bass"]
        )

    files = []
    for part, events in all_events.items():
        if not events:
            continue
        events = _scale_velocity(events, part)
        events = _drop_quiet(events)
        filename = f"{part}.mid"
        out_path = output_dir / filename
        write_midi(events, out_path, bpm=bpm, program=programs.get(part))
        files.append(FileInfo(part=part, filename=filename, url=f"/exports/{gen_id}/{filename}"))

    # Combined export
    if len(all_events) > 1:
        combined_path = output_dir / "combined.mid"
        clean_events = {p: _drop_quiet(_scale_velocity(e, p)) for p, e in all_events.items()}
        write_combined_midi(clean_events, combined_path, bpm=bpm, programs=programs)
        files.append(FileInfo(part="combined", filename="combined.mid", url=f"/exports/{gen_id}/combined.mid"))

    return GenerateResponse(
        generation_id=gen_id,
        style=req.style_id,
        files=files,
        summary=GenerateSummary(
            key=f"{req.key} {req.scale}",
            key_root=req.key,
            scale=req.scale,
            bpm=bpm,
            bars=req.bars,
            complexity=req.complexity,
            variation=req.variation,
            mode=req.mode,
        ),
        seed=seed,
    )


@router.post("/regenerate-part", response_model=FileInfo)
def regenerate_part(req: RegeneratePartRequest):
    output_dir = EXPORTS_DIR / req.generation_id
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail="Generation not found")

    try:
        style = load_style(req.style_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = max(bpm_min, min(bpm_max, req.bpm))

    # Replay the original seed so we pick the same progression and substitutions —
    # keeps harmony consistent with the other parts generated from that seed.
    random.seed(req.seed)
    templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
    progression = random.choice(templates)
    hrb = style.get("harmonic_rhythm_bars", 1)
    if hrb > 1:
        progression = [chord for chord in progression for _ in range(hrb)]

    secondary_dominants = style.get("secondary_dominants", False)

    # New independent seed for just this part — use OS entropy so it's different
    # every call regardless of what req.seed was.
    new_seed = secrets.randbelow(2**31)
    random.seed(new_seed)

    programs: dict[str, int] = {**_DEFAULT_PROGRAMS, **_STYLE_PROGRAMS.get(req.style_id, {})}
    if req.mode == "loop":
        sections = [{"bars": req.bars, "complexity": req.complexity, "parts": [req.part], "offset": 0}]
    else:
        sections = _plan_sections(req.bars, req.complexity, [req.part])
    events: list[NoteEvent] = []

    # Detect if melody.mid already exists alongside the regenerated part so
    # arpeggio can be pushed to a higher octave to avoid register conflict.
    melody_exists = (output_dir / "melody.mid").exists()

    for section in sections:
        s_bars  = section["bars"]
        s_cplx  = section["complexity"]
        s_parts = set(section["parts"])
        s_off   = section["offset"]
        if req.part not in s_parts:
            continue

        # Re-resolve substitutions with this section's complexity so the
        # regenerated part stays harmonically aligned with the original session.
        s_resolved = resolve_progression(progression, req.scale, s_cplx, secondary_dominants)

        if req.part == "chords":
            evts = generate_chords(style, req.key, req.scale, s_bars, s_cplx,
                                   req.variation, progression, s_resolved)
        elif req.part == "bass":
            evts = generate_bass(style, req.key, req.scale, s_bars, s_cplx,
                                 req.variation, progression)
        elif req.part == "melody":
            evts = generate_melody(style, req.key, req.scale, s_bars, s_cplx,
                                   req.variation, s_resolved)
        elif req.part == "drums":
            evts = generate_drums(style, s_bars, s_cplx, req.variation,
                                  section_end_bars=_section_end_bars(sections, s_off))
        elif req.part == "arpeggio":
            arp_octave = 6 if melody_exists else 5
            evts = generate_arpeggio(style, req.key, req.scale, s_bars, s_cplx,
                                     req.variation, s_resolved, arp_octave)
        else:
            continue
        events.extend(_shift(evts, s_off))

    events = _scale_velocity(events, req.part)
    events = _drop_quiet(events)

    filename = f"{req.part}.mid"
    out_path = output_dir / filename
    write_midi(events, out_path, bpm=bpm, program=programs.get(req.part))

    # Rebuild combined.mid so it reflects the newly regenerated part
    rebuild_combined_from_parts(output_dir, bpm)

    return FileInfo(part=req.part, filename=filename, url=f"/exports/{req.generation_id}/{filename}")


@router.get("/exports/{gen_id}/{filename}")
def download_export(gen_id: str, filename: str):
    file_path = EXPORTS_DIR / gen_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path), media_type="audio/midi", filename=filename)
