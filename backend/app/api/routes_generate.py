import concurrent.futures
import io
import logging
import random
import re
import secrets
import uuid
import json as _json_module
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from app.models.schemas import GenerateRequest, RegeneratePartRequest, GenerateResponse, FileInfo, GenerateSummary, QualityScore, BatchGenerateRequest
from app.services.style_loader import load_style
from app.services.midi_writer import NoteEvent, ControlEvent, PitchBendEvent, write_midi, write_combined_midi, rebuild_combined_from_parts, concatenate_midi_files
from app.generators.chords import generate_chords, resolve_progression
from app.generators.bass import generate_bass
from app.generators.melody import generate_melody
from app.generators.drums import generate_drums
from app.generators.arpeggio import generate_arpeggio
from app.core.config import EXPORTS_DIR
from app.core.constants import DRUM_MAP
from app.services.quality import score_generation, extract_rhythm_patterns
from app.services.library import save_generation as lib_save, is_saved, build_scoring_style

router = APIRouter()
logger = logging.getLogger(__name__)

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
    "afrobeats":  {"chords": 24, "bass": 33, "melody": 56, "arpeggio": 24},
    "cumbia":     {"chords": 23, "bass": 33, "melody": 73, "arpeggio": 23},
    "reggaeton":  {"chords": 90, "bass": 38, "melody": 80, "arpeggio": 80},
    "dancehall":  {"chords": 90, "bass": 38, "melody": 80, "arpeggio": 80},
    # New styles
    "grime":       {"chords": 90, "bass": 38, "melody": 80},
    "hyperpop":    {"chords": 90, "bass": 38, "melody": 81, "arpeggio": 80},
    "baile_funk":  {"chords": 5,  "bass": 33, "melody": 80},
    "samba":       {"chords": 25, "bass": 32, "melody": 73, "arpeggio": 25},
    "afropop":     {"chords": 24, "bass": 33, "melody": 56, "arpeggio": 24},
}

_VELOCITY_DROP = 20  # notes quieter than this are inaudible — discard them

# How each section type shapes the generated loop.
# complexity_scale / variation_scale multiply the user's sliders.
# velocity_scale is applied to all note events after generation.
# melody_complexity_scale / backing_complexity_scale override per-part
# complexity for instrumental_solo (melody leads, chords/bass serve as backing).
SECTION_PROFILES: dict[str, dict] = {
    "intro": {
        "bars_typical": [4, 8],
        "complexity_scale": 0.60,
        "variation_scale": 0.80,
        "velocity_scale": 0.80,
        "melody_complexity_scale": 0.40,
    },
    "verse": {
        "bars_typical": [8, 16],
        "complexity_scale": 0.82,
        "variation_scale": 0.90,
        "velocity_scale": 0.87,
    },
    "pre_chorus": {
        "bars_typical": [2, 4],
        "complexity_scale": 1.00,
        "variation_scale": 1.10,
        "velocity_scale": 0.93,
    },
    "chorus": {
        "bars_typical": [4, 8],
        "complexity_scale": 1.12,
        "variation_scale": 0.85,
        "velocity_scale": 1.00,
    },
    "post_chorus": {
        "bars_typical": [2, 4],
        "complexity_scale": 1.05,
        "variation_scale": 0.80,
        "velocity_scale": 0.97,
    },
    "bridge": {
        "bars_typical": [4, 8],
        "complexity_scale": 0.90,
        "variation_scale": 1.20,
        "velocity_scale": 0.88,
    },
    "instrumental_solo": {
        "bars_typical": [4, 16],
        "complexity_scale": 0.90,
        "variation_scale": 1.10,
        "velocity_scale": 0.95,
        "melody_complexity_scale": 1.40,
        "backing_complexity_scale": 0.60,
    },
    "outro": {
        "bars_typical": [4, 16],
        "complexity_scale": 0.55,
        "variation_scale": 0.70,
        "velocity_scale": 0.78,
    },
}

# Per-part velocity scale factors. Bass sits loudest, chords slightly back,
# melody present above chords, arpeggio light. Drums are not scaled.
_VELOCITY_SCALE: dict[str, float] = {
    "bass":     0.88,
    "chords":   0.68,
    "melody":   1.00,
    "arpeggio": 0.62,
}

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _part_seed(main_seed: int, section_idx: int, part: str) -> int:
    """Derive a deterministic seed for a specific section × part pair.

    Seeding each generator independently means adding or removing a part cannot
    affect the random state seen by any other part, making generation fully
    reproducible from the main seed.
    """
    return abs(hash((main_seed, section_idx, part))) % (2 ** 31)


def _transpose_key(key: str, semitones: int) -> str:
    from app.theory.notes import note_name_to_midi
    pc = note_name_to_midi(key, 4) % 12
    return _NOTE_NAMES[(pc + semitones) % 12]


_PART_PAN = {"bass": 64, "chords": 54, "melody": 70, "arpeggio": 74}
_PART_CHANNELS = {"chords": 0, "bass": 1, "melody": 2, "arpeggio": 3}


def _generate_part_cc(part: str, total_bars: int, channel: int) -> list[ControlEvent]:
    """Generate pan (CC10) for all parts and sustain pedal (CC64) for chords."""
    cc: list[ControlEvent] = []
    cc.append(ControlEvent(control=10, value=_PART_PAN.get(part, 64), start=0.0, channel=channel))
    if part == "chords":
        for bar in range(total_bars):
            b = float(bar * 4)
            cc.append(ControlEvent(control=64, value=127, start=b, channel=channel))
            cc.append(ControlEvent(control=64, value=0, start=b + 3.75, channel=channel))
    return cc


def _generate_melody_expression_cc(events: list[NoteEvent], channel: int) -> list[ControlEvent]:
    """Generate CC11 (Expression) swells for melody notes — swell on attack, decay on release."""
    cc: list[ControlEvent] = []
    for note in sorted(events, key=lambda e: e.start):
        d = note.duration
        if d <= 0.5:
            cc.append(ControlEvent(control=11, value=90, start=note.start, channel=channel))
        elif d <= 2.0:
            cc.append(ControlEvent(control=11, value=65,  start=note.start,           channel=channel))
            cc.append(ControlEvent(control=11, value=115, start=note.start + d * 0.25, channel=channel))
            cc.append(ControlEvent(control=11, value=80,  start=note.start + d * 0.85, channel=channel))
        else:
            cc.append(ControlEvent(control=11, value=50,  start=note.start,           channel=channel))
            cc.append(ControlEvent(control=11, value=127, start=note.start + d * 0.15, channel=channel))
            cc.append(ControlEvent(control=11, value=100, start=note.start + d * 0.65, channel=channel))
            cc.append(ControlEvent(control=11, value=65,  start=note.start + d * 0.90, channel=channel))
    return cc


def _generate_808_pitch_bends(events: list[NoteEvent], channel: int) -> list[PitchBendEvent]:
    """Pitch bend slide-in curves for 808 bass notes (±2 semitone range assumed)."""
    pb: list[PitchBendEvent] = []
    for e in sorted(events, key=lambda x: x.start):
        t = e.start
        # Reset to 0 just before each slide starts (prevents carry-over from previous note)
        pb.append(PitchBendEvent(0,     max(0.0, t - 0.09), channel))
        pb.append(PitchBendEvent(-3000, max(0.0, t - 0.05), channel))
        pb.append(PitchBendEvent(-1500, t + 0.04,            channel))
        pb.append(PitchBendEvent(-300,  t + 0.10,            channel))
        pb.append(PitchBendEvent(0,     t + 0.16,            channel))
    return pb


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


def _plan_sections(total_bars: int, complexity: float, requested_parts: list[str],
                   base_key: str = "C", key_shift: int = 0) -> list[dict]:
    """Return an arrangement arc as a list of section dicts.

    Each dict has: bars, complexity, parts, offset (in beats).
    Sections progress from sparse (foundation only) → full arrangement → sparse outro,
    so the output feels like a song with an energy curve rather than a looping pattern.
    """
    full   = list(requested_parts)
    no_arp = [p for p in requested_parts if p != "arpeggio"]
    sparse = [p for p in requested_parts if p in ("drums", "bass", "chords")]
    found  = [p for p in requested_parts if p in ("drums", "bass")]

    chorus_key = _transpose_key(base_key, key_shift) if key_shift else base_key

    def sec(b: int, c_mul: float, p: list, off: int, key: str = base_key, dyn: float = 1.0) -> dict:
        return {"bars": b, "complexity": max(0.1, complexity * c_mul), "parts": p, "offset": off, "key": key, "dynamic": dyn}

    if total_bars <= 4:
        return [sec(total_bars, 1.0, full, 0, dyn=1.0)]

    if total_bars <= 8:
        intro = max(1, total_bars // 4)
        return [
            sec(intro,              0.35, found, 0,          dyn=0.72),
            sec(total_bars - intro, 1.0,  full,  intro * 4,  dyn=1.0),
        ]

    if total_bars <= 16:
        intro  = max(1, total_bars // 6)
        outro  = intro
        mid    = total_bars - intro - outro
        verse  = mid // 2
        chorus = mid - verse
        secs, off = [], 0
        secs.append(sec(intro,  0.3,  found,  off, dyn=0.70)); off += intro  * 4
        secs.append(sec(verse,  0.65, sparse, off, dyn=0.85)); off += verse  * 4
        secs.append(sec(chorus, 1.0,  full,   off, key=chorus_key, dyn=1.00)); off += chorus * 4
        secs.append(sec(outro,  0.35, found,  off, dyn=0.72))
        return secs

    # 17+ bars: full song arc — intro, verse, chorus, outro
    intro  = 2
    outro  = 2
    mid    = total_bars - intro - outro
    verse  = mid // 3
    chorus = mid - verse
    secs, off = [], 0
    secs.append(sec(intro,  0.25, found,  off, dyn=0.70)); off += intro  * 4
    secs.append(sec(verse,  0.6,  no_arp, off, dyn=0.85)); off += verse  * 4
    secs.append(sec(chorus, 1.0,  full,   off, key=chorus_key, dyn=1.00)); off += chorus * 4
    secs.append(sec(outro,  0.3,  found,  off, dyn=0.72))
    return secs


_MAX_QUALITY_ATTEMPTS = 5
_GREEN_THRESHOLD = 0.82
_GENERATION_TIMEOUT_S = 30
_QUALITY_DIMS = ("harmonic", "register", "rhythm", "density", "mix")


def _all_green(quality_raw: dict) -> bool:
    return all(quality_raw.get(d, 0.0) >= _GREEN_THRESHOLD for d in _QUALITY_DIMS)


def _apply_groove_push(events: list[NoteEvent], push: float) -> list[NoteEvent]:
    """Shift all notes by a systematic beat offset.

    Negative push = behind the beat (lazy hip-hop/jazz feel).
    Positive push = ahead of the beat (forward funk/soul feel).
    Applied to melodic parts only (drums are the timing reference).
    """
    if abs(push) < 0.0005:
        return events
    return [
        NoteEvent(e.pitch, max(0.0, e.start + push), e.duration, e.velocity, e.channel)
        for e in events
    ]


def _apply_dynamic(events: list[NoteEvent], factor: float) -> list[NoteEvent]:
    """Scale all note velocities by a section-level dynamic factor."""
    if abs(factor - 1.0) < 0.01:
        return events
    return [
        NoteEvent(e.pitch, e.start, e.duration, max(1, min(127, int(e.velocity * factor))), e.channel)
        for e in events
    ]


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


def _run_attempt(
    req,
    style: dict,
    seed: int,
    is_loop: bool,
    groove_push: float,
    secondary_dominants: bool,
    tritone_sub: bool,
    scoring_style: dict | None = None,
) -> tuple[dict, dict, dict, list, dict | None, dict, list]:
    """Run one generation attempt for a given seed.

    Returns (all_events, cc_parts, pb_parts, progression, quality_raw, patterns).
    quality_raw is None if scoring raised an exception.
    scoring_style overrides the style dict used for quality scoring only,
    so learned patterns can improve scorer accuracy without touching generation.
    """
    templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
    random.seed(seed)
    progression = random.choice(templates)
    hrb = style.get("harmonic_rhythm_bars", 1)
    if hrb > 1:
        progression = [chord for chord in progression for _ in range(hrb)]

    # Resolve section profile for loop-mode shaping
    _sec_profile = SECTION_PROFILES.get(req.section_type or "", {}) if is_loop else {}
    _sec_cplx = min(1.0, req.complexity * _sec_profile.get("complexity_scale", 1.0))
    _sec_var  = min(1.0, req.variation  * _sec_profile.get("variation_scale",  1.0))
    _sec_dyn  = _sec_profile.get("velocity_scale", 1.0)

    if is_loop:
        sections = [{"bars": req.bars, "complexity": _sec_cplx, "parts": req.parts,
                     "offset": 0, "key": req.key, "dynamic": _sec_dyn}]
    else:
        key_shift = style.get("chorus_key_shift", 0)
        sections = _plan_sections(req.bars, req.complexity, req.parts, req.key, key_shift)

    all_events: dict[str, list[NoteEvent]] = {part: [] for part in req.parts}

    for section_i, section in enumerate(sections):
        s_bars  = section["bars"]
        s_cplx  = section["complexity"]
        s_parts = set(section["parts"])
        s_off   = section["offset"]
        s_key   = section.get("key", req.key)

        random.seed(_part_seed(seed, section_i, "harmony"))
        s_resolved = resolve_progression(progression, req.scale, s_cplx, secondary_dominants, tritone_sub)

        s_dyn = section.get("dynamic", 1.0)
        is_outro = (section_i == len(sections) - 1 and s_cplx < 0.5 and s_bars >= 2)
        bass_prog = (["I"] * len(progression)) if is_outro else progression

        # Per-part complexity / variation overrides from section profile (loop mode only)
        eff_var      = _sec_var if is_loop else req.variation
        mel_cplx     = min(1.0, s_cplx * _sec_profile.get("melody_complexity_scale",  1.0))
        backing_cplx = min(1.0, s_cplx * _sec_profile.get("backing_complexity_scale", 1.0))

        kick_times: list[float] = []
        if "drums" in req.parts and "drums" in s_parts:
            random.seed(_part_seed(seed, section_i, "drums"))
            drum_evts = generate_drums(style, s_bars, s_cplx, eff_var,
                                       section_end_bars=_section_end_bars(sections, s_off),
                                       is_loop=is_loop)
            drum_evts = _apply_dynamic(drum_evts, s_dyn)
            all_events["drums"].extend(_shift(drum_evts, s_off))
            kick_times = [e.start for e in drum_evts if e.pitch == DRUM_MAP["kick"]]

        has_melody = "melody" in s_parts
        mel_range = style.get("melody", {}).get("range", [60, 79])
        # Apply melody_ceiling only for styles that explicitly set a high chord_register
        # (synthwave, house, future_bass, etc. that use pads in the melody's range).
        # Low-register styles (jazz, lofi, etc.) use the default [48,72] chord range
        # which already sits below melody without needing a ceiling.
        has_custom_chord_register = "chord_register" in style
        chord_avg_register = sum(style["chord_register"]) / 2 if has_custom_chord_register else 0
        melody_ceiling = (
            mel_range[0]
            if (has_melody and has_custom_chord_register and chord_avg_register > mel_range[0])
            else None
        )

        mel_rests: list = []
        if has_melody and "melody" in req.parts:
            random.seed(_part_seed(seed, section_i, "melody"))
            mel_evts = generate_melody(style, s_key, req.scale, s_bars, mel_cplx,
                                       eff_var, s_resolved, is_loop=is_loop)
            mel_evts = _apply_dynamic(mel_evts, s_dyn)
            all_events["melody"].extend(_shift(mel_evts, s_off))
            if mel_evts:
                sorted_mel = sorted(mel_evts, key=lambda e: e.start)
                for _i in range(1, len(sorted_mel)):
                    gap_s = sorted_mel[_i - 1].start + sorted_mel[_i - 1].duration
                    gap_e = sorted_mel[_i].start
                    if gap_e - gap_s >= 1.5:
                        mel_rests.append((round(gap_s, 3), round(gap_e, 3)))

        for part in req.parts:
            if part in ("drums", "melody") or part not in s_parts:
                continue
            random.seed(_part_seed(seed, section_i, part))
            if part == "chords":
                evts = generate_chords(style, s_key, req.scale, s_bars, backing_cplx,
                                       eff_var, progression, s_resolved,
                                       melody_ceiling=melody_ceiling)
            elif part == "bass":
                evts = generate_bass(style, s_key, req.scale, s_bars, backing_cplx,
                                     eff_var, bass_prog, kick_times,
                                     melody_rests=mel_rests)
            elif part == "arpeggio":
                arp_octave = 6 if has_melody else 5
                evts = generate_arpeggio(style, s_key, req.scale, s_bars, backing_cplx,
                                         eff_var, s_resolved, arp_octave)
            else:
                continue
            evts = _apply_dynamic(evts, s_dyn)
            all_events[part].extend(_shift(evts, s_off))

    if groove_push:
        for gp_part in ("melody", "chords", "arpeggio", "bass"):
            if gp_part in all_events and all_events[gp_part]:
                all_events[gp_part] = _apply_groove_push(all_events[gp_part], groove_push)

    if "melody" in all_events and "bass" in all_events:
        all_events["melody"] = _prevent_parallel_motion(
            all_events["melody"], all_events["bass"]
        )

    cc_parts: dict[str, list[ControlEvent]] = {}
    for part in req.parts:
        if part == "drums" or part not in all_events or not all_events[part]:
            continue
        channel = _PART_CHANNELS.get(part, 0)
        cc_parts[part] = _generate_part_cc(part, req.bars, channel)

    if "melody" in all_events and all_events["melody"]:
        ch = _PART_CHANNELS.get("melody", 2)
        melody_cc11 = _generate_melody_expression_cc(all_events["melody"], ch)
        cc_parts.setdefault("melody", []).extend(melody_cc11)

    pb_parts: dict[str, list[PitchBendEvent]] = {}
    if "bass" in all_events and all_events["bass"]:
        bass_cfg = style.get("bass", {})
        if bass_cfg.get("bass_style") == "808":
            ch = _PART_CHANNELS.get("bass", 1)
            pb_parts["bass"] = _generate_808_pitch_bends(all_events["bass"], ch)

    patterns = extract_rhythm_patterns(all_events, req.bars)

    # Pre-apply the same velocity scaling used for MIDI output so the mix scorer
    # evaluates what the listener will actually hear, not the raw generator values.
    _scored_events = {
        part: [
            NoteEvent(e.pitch, e.start, e.duration,
                      max(1, min(127, int(e.velocity * _VELOCITY_SCALE.get(part, 1.0)))),
                      e.channel)
            for e in evts
        ]
        for part, evts in all_events.items()
    }

    try:
        quality_raw = score_generation(
            _scored_events, scoring_style or style,
            req.key, req.scale, req.bars, progression, req.complexity
        )
    except Exception as exc:
        logger.error("Quality scoring failed (seed=%s): %s", seed, exc, exc_info=True)
        quality_raw = None

    return all_events, cc_parts, pb_parts, progression, quality_raw, patterns, sections


@router.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    try:
        style = load_style(req.style_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = max(bpm_min, min(bpm_max, req.bpm))

    gen_id = str(uuid.uuid4())[:8]
    output_dir = EXPORTS_DIR / gen_id
    output_dir.mkdir(parents=True, exist_ok=True)

    programs: dict[str, int] = {**_DEFAULT_PROGRAMS, **_STYLE_PROGRAMS.get(req.style_id, {})}

    secondary_dominants = style.get("secondary_dominants", False)
    tritone_sub = style.get("tritone_substitution", False)
    is_loop = (req.mode == "loop")
    groove_push = style.get("groove_push", 0.0)

    # Blend two styles if requested
    if req.blend_style_id and req.blend_style_id != req.style_id:
        try:
            b_style = load_style(req.blend_style_id)
            w = req.blend_amount
            _NUMERIC_BLEND = ("hat_density", "kick_density", "snare_density",
                              "swing", "syncopation_prob", "groove_push")
            blended = {**style}
            for key in _NUMERIC_BLEND:
                if key in style and key in b_style:
                    blended[key] = (1 - w) * style[key] + w * b_style[key]
            # Merge progression templates
            a_progs = style.get("progression_templates", [])
            b_progs = b_style.get("progression_templates", [])
            if a_progs and b_progs:
                blended["progression_templates"] = a_progs + b_progs
            # Blend drum configs numerically
            if "drums" in style and "drums" in b_style:
                d_a, d_b = style["drums"], b_style["drums"]
                drum_blend = {**d_a}
                for k in ("hat_density", "kick_density", "snare_density", "swing",
                          "triplet_probability", "ghost_probability"):
                    if k in d_a and k in d_b:
                        drum_blend[k] = (1 - w) * d_a[k] + w * d_b[k]
                blended["drums"] = drum_blend
            style = blended
        except ValueError:
            logger.warning("Blend style %r not found — ignoring blend", req.blend_style_id)

    # Inject humanize scale so generators can read it without API changes
    style = {**style, "_humanize_scale": req.humanize}

    # Use custom progression if provided (validate roman numerals loosely)
    if req.custom_progression:
        style = {**style, "progression_templates": [req.custom_progression]}

    # Use library-learned patterns to sharpen the scorer's rhythm references
    scoring_style = build_scoring_style(style, req.style_id)

    # Start with the requested seed (or a fresh random one)
    base_seed = req.seed if req.seed is not None else random.randint(0, 2**31 - 1)

    def _run_best_attempt():
        _best_events = _best_cc = _best_pb = _best_progression = _best_quality_raw = _best_patterns = None
        _best_seed = base_seed
        for attempt in range(_MAX_QUALITY_ATTEMPTS):
            attempt_seed = base_seed if attempt == 0 else random.randint(0, 2**31 - 1)
            _evts, _cc, _pb, _prog, _qraw, _pats, _secs = _run_attempt(
                req, style, attempt_seed, is_loop, groove_push, secondary_dominants, tritone_sub,
                scoring_style=scoring_style,
            )
            if _best_quality_raw is None or (
                _qraw is not None and _qraw.get("total", 0) > _best_quality_raw.get("total", 0)
            ):
                _best_events, _best_cc, _best_pb = _evts, _cc, _pb
                _best_progression, _best_quality_raw = _prog, _qraw
                _best_patterns, _best_sections = _pats, _secs
                _best_seed = attempt_seed
            if _qraw is not None and _all_green(_qraw):
                _best_seed = attempt_seed
                break
        return _best_events, _best_cc, _best_pb, _best_progression, _best_quality_raw, _best_patterns, _best_sections, _best_seed

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
            _fut = _pool.submit(_run_best_attempt)
            (best_events, best_cc, best_pb, best_progression,
             best_quality_raw, best_patterns, best_sections, best_seed) = _fut.result(timeout=_GENERATION_TIMEOUT_S)
    except concurrent.futures.TimeoutError:
        raise HTTPException(status_code=504, detail=f"Generation timed out after {_GENERATION_TIMEOUT_S}s")

    all_events  = best_events
    cc_parts    = best_cc
    pb_parts    = best_pb
    progression = best_progression
    quality_raw = best_quality_raw
    patterns    = best_patterns
    seed        = best_seed

    quality = QualityScore(**quality_raw) if quality_raw else None

    import json as _json

    # Write patterns.json so the frontend's manual-save can retrieve them later
    (output_dir / "patterns.json").write_text(_json.dumps(patterns or {}))

    # Auto-save to library when all dimensions are green
    if quality_raw and _all_green(quality_raw):
        try:
            lib_save(
                gen_id=gen_id,
                style_id=req.style_id,
                key=req.key,
                scale=req.scale,
                bpm=bpm,
                bars=req.bars,
                seed=seed,
                quality_raw=quality_raw,
                patterns=patterns or {},
            )
        except Exception as exc:
            logger.warning("Library auto-save failed for gen_id=%s: %s", gen_id, exc)

    files = []
    for part, events in all_events.items():
        if not events:
            continue
        events = _scale_velocity(events, part)
        events = _drop_quiet(events)
        filename = f"{part}.mid"
        out_path = output_dir / filename
        write_midi(events, out_path, bpm=bpm, program=programs.get(part),
                   cc_events=cc_parts.get(part), pb_events=pb_parts.get(part))
        files.append(FileInfo(part=part, filename=filename, url=f"/exports/{gen_id}/{filename}"))

    if len(all_events) > 1:
        combined_path = output_dir / "combined.mid"
        clean_events = {p: _drop_quiet(_scale_velocity(e, p)) for p, e in all_events.items()}
        write_combined_midi(clean_events, combined_path, bpm=bpm, programs=programs,
                           cc_parts=cc_parts, pb_parts=pb_parts)
        files.append(FileInfo(part="combined", filename="combined.mid", url=f"/exports/{gen_id}/combined.mid"))

    # In arrangement mode, also write per-section MIDI files
    if not is_loop and best_sections:
        sec_dir = output_dir / "sections"
        sec_dir.mkdir(exist_ok=True)
        import json as _js
        section_meta = []
        for sec_i, sec in enumerate(best_sections):
            sec_start = float(sec["offset"])
            sec_end = sec_start + sec["bars"] * 4.0
            sec_name = sec.get("section_type", f"section_{sec_i + 1}")
            sec_evts: dict[str, list] = {}
            for part, evts in all_events.items():
                clipped = [
                    NoteEvent(e.pitch, e.start - sec_start, e.duration, e.velocity, e.channel)
                    for e in evts
                    if sec_start <= e.start < sec_end
                ]
                if clipped:
                    sec_evts[part] = _drop_quiet(_scale_velocity(clipped, part))
            if sec_evts:
                sec_combined = sec_dir / f"{sec_i + 1:02d}_{sec_name}_combined.mid"
                write_combined_midi(sec_evts, sec_combined, bpm=bpm, programs=programs)
                section_meta.append({
                    "index": sec_i + 1, "name": sec_name,
                    "bars": sec["bars"], "bpm": bpm,
                    "file": sec_combined.name,
                })
        (sec_dir / "sections.json").write_text(_js.dumps(section_meta, indent=2))

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
            section_type=req.section_type,
        ),
        seed=seed,
        quality=quality,
        auto_saved=bool(quality_raw and _all_green(quality_raw)),
        progression=progression,
    )


@router.post("/generate-stream")
def generate_stream(req: GenerateRequest):
    """SSE endpoint: streams attempt progress then the final GenerateResponse."""
    def event_stream():
        try:
            style = load_style(req.style_id)
        except ValueError as e:
            yield f"data: {_json_module.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        bpm_min, bpm_max = style.get("bpm_range", [40, 240])
        bpm = max(bpm_min, min(bpm_max, req.bpm))
        gen_id = str(uuid.uuid4())[:8]
        output_dir = EXPORTS_DIR / gen_id
        output_dir.mkdir(parents=True, exist_ok=True)

        programs = {**_DEFAULT_PROGRAMS, **_STYLE_PROGRAMS.get(req.style_id, {})}
        secondary_dominants = style.get("secondary_dominants", False)
        tritone_sub = style.get("tritone_substitution", False)
        is_loop = (req.mode == "loop")
        groove_push = style.get("groove_push", 0.0)
        style = {**style, "_humanize_scale": req.humanize}
        if req.custom_progression:
            style = {**style, "progression_templates": [req.custom_progression]}
        scoring_style = build_scoring_style(style, req.style_id)
        base_seed = req.seed if req.seed is not None else random.randint(0, 2**31 - 1)

        best_events = best_cc = best_pb = best_progression = best_quality_raw = best_patterns = None
        best_seed = base_seed

        for attempt in range(_MAX_QUALITY_ATTEMPTS):
            attempt_seed = base_seed if attempt == 0 else random.randint(0, 2**31 - 1)
            yield f"data: {_json_module.dumps({'type': 'progress', 'attempt': attempt + 1, 'total': _MAX_QUALITY_ATTEMPTS})}\n\n"
            try:
                evts, cc, pb, prog, qraw, pats, secs = _run_attempt(
                    req, style, attempt_seed, is_loop, groove_push,
                    secondary_dominants, tritone_sub, scoring_style=scoring_style,
                )
            except Exception as exc:
                logger.error("Attempt %d failed: %s", attempt + 1, exc, exc_info=True)
                continue
            if best_quality_raw is None or (qraw and qraw.get("total", 0) > best_quality_raw.get("total", 0)):
                best_events, best_cc, best_pb = evts, cc, pb
                best_progression, best_quality_raw, best_patterns = prog, qraw, pats
                best_seed = attempt_seed
            if qraw and _all_green(qraw):
                best_seed = attempt_seed
                break

        quality = QualityScore(**best_quality_raw) if best_quality_raw else None
        if best_quality_raw and _all_green(best_quality_raw):
            try:
                lib_save(gen_id=gen_id, style_id=req.style_id, key=req.key, scale=req.scale,
                         bpm=bpm, bars=req.bars, seed=best_seed,
                         quality_raw=best_quality_raw, patterns=best_patterns or {})
            except Exception as exc:
                logger.warning("Library auto-save failed: %s", exc)
        (output_dir / "patterns.json").write_text(_json_module.dumps(best_patterns or {}))

        files = []
        for part, events in (best_events or {}).items():
            if not events:
                continue
            events = _scale_velocity(events, part)
            events = _drop_quiet(events)
            filename = f"{part}.mid"
            write_midi(events, output_dir / filename, bpm=bpm,
                       program=programs.get(part),
                       cc_events=(best_cc or {}).get(part),
                       pb_events=(best_pb or {}).get(part))
            files.append(FileInfo(part=part, filename=filename, url=f"/exports/{gen_id}/{filename}"))

        if best_events and len(best_events) > 1:
            combined_path = output_dir / "combined.mid"
            clean = {p: _drop_quiet(_scale_velocity(e, p)) for p, e in best_events.items()}
            write_combined_midi(clean, combined_path, bpm=bpm, programs=programs,
                               cc_parts=best_cc or {}, pb_parts=best_pb or {})
            files.append(FileInfo(part="combined", filename="combined.mid",
                                  url=f"/exports/{gen_id}/combined.mid"))

        response = GenerateResponse(
            generation_id=gen_id, style=req.style_id, files=files,
            summary=GenerateSummary(key=f"{req.key} {req.scale}", key_root=req.key,
                                    scale=req.scale, bpm=bpm, bars=req.bars,
                                    complexity=req.complexity, variation=req.variation,
                                    mode=req.mode, section_type=req.section_type),
            seed=best_seed, quality=quality,
            auto_saved=bool(best_quality_raw and _all_green(best_quality_raw)),
            progression=best_progression or [],
        )
        yield f"data: {_json_module.dumps({'type': 'done', 'result': response.model_dump()})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/batch-generate", response_model=list[GenerateResponse])
def batch_generate(req: BatchGenerateRequest):
    """Run `count` independent generations and return all results sorted best-first."""
    results = []
    for _ in range(req.count):
        seed_req = GenerateRequest(**{**req.base.model_dump(), "seed": None})
        results.append(generate(seed_req))
    results.sort(key=lambda r: r.quality.total if r.quality else 0.0, reverse=True)
    return results


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
    tritone_sub = style.get("tritone_substitution", False)

    # New independent seed for just this part — use OS entropy so it's different
    # every call regardless of what req.seed was.
    new_seed = secrets.randbelow(2**31)
    random.seed(new_seed)

    programs: dict[str, int] = {**_DEFAULT_PROGRAMS, **_STYLE_PROGRAMS.get(req.style_id, {})}
    if req.mode == "loop":
        sections = [{"bars": req.bars, "complexity": req.complexity, "parts": [req.part], "offset": 0, "key": req.key}]
    else:
        key_shift = style.get("chorus_key_shift", 0)
        sections = _plan_sections(req.bars, req.complexity, [req.part], req.key, key_shift)
    events: list[NoteEvent] = []

    # Detect if melody.mid already exists alongside the regenerated part so
    # arpeggio can be pushed to a higher octave to avoid register conflict.
    melody_exists = (output_dir / "melody.mid").exists()

    for section_i, section in enumerate(sections):
        s_bars  = section["bars"]
        s_cplx  = section["complexity"]
        s_parts = set(section["parts"])
        s_off   = section["offset"]
        s_key   = section.get("key", req.key)
        if req.part not in s_parts:
            continue

        # Re-resolve substitutions with this section's complexity so the
        # regenerated part stays harmonically aligned with the original session.
        s_resolved = resolve_progression(progression, req.scale, s_cplx, secondary_dominants, tritone_sub)

        kick_times: list[float] = []
        if req.part == "bass":
            saved_state = random.getstate()
            random.seed(_part_seed(req.seed, section_i, "drums"))
            drum_evts_tmp = generate_drums(style, s_bars, s_cplx, req.variation,
                                           section_end_bars=_section_end_bars(sections, s_off))
            kick_times = [e.start for e in drum_evts_tmp if e.pitch == DRUM_MAP["kick"]]
            random.setstate(saved_state)

        s_dyn = section.get("dynamic", 1.0)

        if req.part == "chords":
            evts = generate_chords(style, s_key, req.scale, s_bars, s_cplx,
                                   req.variation, progression, s_resolved)
        elif req.part == "bass":
            evts = generate_bass(style, s_key, req.scale, s_bars, s_cplx,
                                 req.variation, progression, kick_times)
        elif req.part == "melody":
            evts = generate_melody(style, s_key, req.scale, s_bars, s_cplx,
                                   req.variation, s_resolved)
        elif req.part == "drums":
            evts = generate_drums(style, s_bars, s_cplx, req.variation,
                                  section_end_bars=_section_end_bars(sections, s_off))
        elif req.part == "arpeggio":
            arp_octave = 6 if melody_exists else 5
            evts = generate_arpeggio(style, s_key, req.scale, s_bars, s_cplx,
                                     req.variation, s_resolved, arp_octave)
        else:
            continue
        evts = _apply_dynamic(evts, s_dyn)
        events.extend(_shift(evts, s_off))

    groove_push = style.get("groove_push", 0.0)
    if groove_push and req.part in ("melody", "chords", "arpeggio", "bass"):
        events = _apply_groove_push(events, groove_push)

    events = _scale_velocity(events, req.part)
    events = _drop_quiet(events)

    channel = _PART_CHANNELS.get(req.part, 0)
    part_cc = _generate_part_cc(req.part, req.bars, channel) if req.part != "drums" else None

    if req.part == "melody" and events:
        cc11 = _generate_melody_expression_cc(events, channel)
        part_cc = (part_cc or []) + cc11

    pb_events = None
    if req.part == "bass":
        bass_cfg = style.get("bass", {})
        if bass_cfg.get("bass_style") == "808":
            pb_events = _generate_808_pitch_bends(events, channel)

    filename = f"{req.part}.mid"
    out_path = output_dir / filename
    write_midi(events, out_path, bpm=bpm, program=programs.get(req.part),
               cc_events=part_cc, pb_events=pb_events)

    # Rebuild combined.mid so it reflects the newly regenerated part
    rebuild_combined_from_parts(output_dir, bpm)

    return FileInfo(part=req.part, filename=filename, url=f"/exports/{req.generation_id}/{filename}")


@router.get("/exports/{gen_id}/bundle.zip")
def download_bundle(gen_id: str):
    import zipfile, io
    output_dir = EXPORTS_DIR / gen_id
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail="Generation not found")
    mid_files = list(output_dir.glob("*.mid"))
    if not mid_files:
        raise HTTPException(status_code=404, detail="No MIDI files found")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(mid_files):
            zf.write(f, f.name)
    buf.seek(0)
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=genregrid_{gen_id}.zip"},
    )


@router.get("/exports/{gen_id}/sections.zip")
def download_sections(gen_id: str):
    import zipfile, io
    sec_dir = EXPORTS_DIR / gen_id / "sections"
    if not sec_dir.exists():
        raise HTTPException(status_code=404, detail="No section stems found — generate in Arrangement mode first")
    mid_files = list(sec_dir.glob("*.mid"))
    if not mid_files:
        raise HTTPException(status_code=404, detail="No section MIDI files found")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(mid_files):
            zf.write(f, f"sections/{f.name}")
        meta = sec_dir / "sections.json"
        if meta.exists():
            zf.write(meta, "sections/sections.json")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=genregrid_{gen_id}_sections.zip"},
    )


@router.get("/exports/{gen_id}/{filename}")
def download_export(gen_id: str, filename: str):
    file_path = EXPORTS_DIR / gen_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path), media_type="audio/midi", filename=filename)


_SAFE_PATH = re.compile(r'^[a-zA-Z0-9_\-]{1,80}$')


class ArrangeEntry(BaseModel):
    generation_id: str
    filename: str


class ArrangeRequest(BaseModel):
    entries: list[ArrangeEntry]


@router.post("/arrange")
def arrange(req: ArrangeRequest):
    """Concatenate multiple MIDI files sequentially into an arrangement."""
    if not req.entries:
        raise HTTPException(400, "No entries provided")

    paths = []
    for entry in req.entries:
        if not _SAFE_PATH.match(entry.generation_id):
            raise HTTPException(400, f"Invalid generation_id: {entry.generation_id!r}")
        safe_name = entry.filename.replace("/", "").replace("\\", "")
        path = EXPORTS_DIR / entry.generation_id / safe_name
        if not path.exists():
            raise HTTPException(404, f"File not found: {entry.generation_id}/{safe_name}")
        paths.append(path)

    try:
        out_mid = concatenate_midi_files(paths)
    except Exception as exc:
        logger.error("arrange failed: %s", exc)
        raise HTTPException(500, "Failed to build arrangement") from exc

    buf = io.BytesIO()
    out_mid.save(file=buf)
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="audio/midi",
        headers={"Content-Disposition": "attachment; filename=arrangement.mid"},
    )
