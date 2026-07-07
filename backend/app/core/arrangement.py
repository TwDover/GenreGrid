# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Song arrangement vocabulary: section profiles, song templates, and the
planning helpers that turn a bar count or template into a section list.

Split out of routes_generate.py so arrangement policy lives apart from the
HTTP endpoints and per-part mixing concerns (see app/services/mixdown.py).
"""
from app.services.midi_writer import NoteEvent


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
        "harmonic_boost": 0.15,
    },
    "chorus": {
        "bars_typical": [4, 8],
        "complexity_scale": 1.12,
        "variation_scale": 0.85,
        "velocity_scale": 1.00,
        # Choruses change chords faster than verses: this boost is added to the
        # complexity value that decides chords-per-bar (shared by chords, bass,
        # and melody so their harmonic grids stay locked together).
        "harmonic_boost": 0.20,
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


def _apply_section_ramp(
    all_events: dict[str, list[NoteEvent]],
    sections: list[dict],
) -> None:
    """Smooth dynamic steps where a section is louder than its predecessor.

    On verse→chorus or intro→verse energy lifts, melodic parts ramp in over
    the first two bars rather than jumping to full level immediately. Drums
    are excluded — they handle the transition via fills.
    """
    for sec_i in range(1, len(sections)):
        prev_dyn = sections[sec_i - 1].get("dynamic", 1.0)
        curr_dyn = sections[sec_i].get("dynamic", 1.0)
        if curr_dyn <= prev_dyn + 0.05:
            continue
        sec_start   = float(sections[sec_i]["offset"])
        ramp_beats  = min(8.0, sections[sec_i]["bars"] * 4 * 0.5)
        start_ratio = prev_dyn / curr_dyn   # factor at the downbeat of the new section
        for part, evts in all_events.items():
            if part == "drums":
                continue
            ramped: list[NoteEvent] = []
            for e in evts:
                if sec_start <= e.start < sec_start + ramp_beats:
                    t_in   = e.start - sec_start
                    factor = start_ratio + (1.0 - start_ratio) * (t_in / ramp_beats)
                    ramped.append(NoteEvent(
                        e.pitch, e.start, e.duration,
                        max(1, min(127, int(e.velocity * factor))), e.channel,
                    ))
                else:
                    ramped.append(e)
            all_events[part] = ramped


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

    # 17-24 bars: compact full arc — 2-bar intro/outro, verse gets 2/3 of middle (min 8)
    if total_bars <= 24:
        intro  = 2
        outro  = 2
        mid    = total_bars - intro - outro
        verse  = max(8, (mid * 2) // 3)
        chorus = mid - verse
        if chorus < 4:
            chorus = 4
            verse  = mid - chorus
        secs, off = [], 0
        secs.append(sec(intro,  0.25, found,  off, dyn=0.70)); off += intro  * 4
        secs.append(sec(verse,  0.6,  no_arp, off, dyn=0.85)); off += verse  * 4
        secs.append(sec(chorus, 1.0,  full,   off, key=chorus_key, dyn=1.00)); off += chorus * 4
        secs.append(sec(outro,  0.3,  found,  off, dyn=0.72))
        return secs

    # 25+ bars: full song arc — 4-bar intro/outro, verse ≥ 16 bars, chorus ≥ 8 bars
    intro  = 4
    outro  = 4
    mid    = total_bars - intro - outro
    verse  = max(16, (mid * 2) // 3)
    chorus = mid - verse
    if chorus < 8:
        chorus = 8
        verse  = mid - chorus
    secs, off = [], 0
    secs.append(sec(intro,  0.25, found,  off, dyn=0.70)); off += intro  * 4
    secs.append(sec(verse,  0.6,  no_arp, off, dyn=0.85)); off += verse  * 4
    secs.append(sec(chorus, 1.0,  full,   off, key=chorus_key, dyn=1.00)); off += chorus * 4
    secs.append(sec(outro,  0.3,  found,  off, dyn=0.72))
    return secs


def _auto_arc_section_type(sections: list[dict], i: int) -> str | None:
    """Map _plan_sections' anonymous arc slots onto section types for the drums.

    The auto-arc has no explicit section names, but its shape is fixed:
    first = intro, last = outro, the loudest middle slot = chorus, rest = verse.
    Returns None for a single-section plan (plain loop — no arrangement context).
    """
    if len(sections) < 2:
        return None
    if i == 0:
        return "intro"
    if i == len(sections) - 1:
        return "outro"
    peak = max(s.get("dynamic", 1.0) for s in sections[1:-1])
    return "chorus" if sections[i].get("dynamic", 1.0) >= peak - 1e-9 else "verse"


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


# ── Full Song Builder ────────────────────────────────────────────────────────
#
# Templates define an ordered sequence of sections. Each entry specifies:
#   section_type  — maps to SECTION_PROFILES for energy/complexity shaping
#   bars          — length of this section
#   parts_mode    — "full" | "no_arp" | "sparse" | "foundation"
#   chorus_key    — True to transpose by style's chorus_key_shift
#
# parts_mode meanings (filtered against the user's selected parts):
#   foundation    drums + bass only
#   sparse        drums + bass + chords
#   no_arp        all parts except arpeggio
#   full          all user-selected parts
#   melodic       chords + melody only (no rhythm section — soft intro/outro)
#   no_drums      all parts except drums (full arrangement, no percussion)
#   chords_only   chords only (solo piano/pad intro)

_SONG_TEMPLATES: dict[str, list[dict]] = {
    # Standard pop/R&B — melodic intro/outro, 16-bar verses.
    "verse_chorus": [
        {"name": "Intro",    "section_type": "intro",   "bars": 4,  "parts_mode": "melodic"},
        {"name": "Verse",    "section_type": "verse",   "bars": 16, "parts_mode": "no_arp"},
        {"name": "Chorus",   "section_type": "chorus",  "bars": 8,  "parts_mode": "full", "chorus_key": True},
        {"name": "Verse 2",  "section_type": "verse",   "bars": 16, "parts_mode": "no_arp"},
        {"name": "Chorus 2", "section_type": "chorus",  "bars": 8,  "parts_mode": "full", "chorus_key": True},
        {"name": "Outro",    "section_type": "outro",   "bars": 4,  "parts_mode": "melodic"},
    ],  # 56 bars
    # Classic pop/rock — fuller no-drum intro, pre-chorus builds, melodic outro.
    "verse_chorus_bridge": [
        {"name": "Intro",         "section_type": "intro",       "bars": 4,  "parts_mode": "no_drums"},
        {"name": "Verse",         "section_type": "verse",       "bars": 16, "parts_mode": "no_arp"},
        {"name": "Pre-Chorus",    "section_type": "pre_chorus",  "bars": 4,  "parts_mode": "sparse"},
        {"name": "Chorus",        "section_type": "chorus",      "bars": 8,  "parts_mode": "full", "chorus_key": True},
        {"name": "Verse 2",       "section_type": "verse",       "bars": 16, "parts_mode": "no_arp"},
        {"name": "Pre-Chorus 2",  "section_type": "pre_chorus",  "bars": 4,  "parts_mode": "sparse"},
        {"name": "Chorus 2",      "section_type": "chorus",      "bars": 8,  "parts_mode": "full", "chorus_key": True},
        {"name": "Bridge",        "section_type": "bridge",      "bars": 8,  "parts_mode": "full", "bridge_key": True},
        {"name": "Final Chorus",  "section_type": "chorus",      "bars": 8,  "parts_mode": "full", "chorus_key": True},
        {"name": "Outro",         "section_type": "outro",       "bars": 4,  "parts_mode": "melodic"},
    ],  # 80 bars
    # Extended with instrumental solo — drums-first intro (electronic/hip-hop feel).
    "extended": [
        {"name": "Intro",         "section_type": "intro",             "bars": 4,  "parts_mode": "foundation"},
        {"name": "Verse",         "section_type": "verse",             "bars": 16, "parts_mode": "sparse"},
        {"name": "Chorus",        "section_type": "chorus",            "bars": 8,  "parts_mode": "full", "chorus_key": True},
        {"name": "Verse 2",       "section_type": "verse",             "bars": 16, "parts_mode": "no_arp"},
        {"name": "Chorus 2",      "section_type": "chorus",            "bars": 8,  "parts_mode": "full", "chorus_key": True},
        {"name": "Instrumental",  "section_type": "instrumental_solo", "bars": 8,  "parts_mode": "full"},
        {"name": "Bridge",        "section_type": "bridge",            "bars": 8,  "parts_mode": "full", "bridge_key": True},
        {"name": "Final Chorus",  "section_type": "chorus",            "bars": 8,  "parts_mode": "full", "chorus_key": True},
        {"name": "Outro",         "section_type": "outro",             "bars": 4,  "parts_mode": "foundation"},
    ],  # 80 bars
    # Compact sketch — 8-bar verses, solo chords intro/outro for a simple feel.
    "compact": [
        {"name": "Intro",    "section_type": "intro",   "bars": 4, "parts_mode": "chords_only"},
        {"name": "Verse",    "section_type": "verse",   "bars": 8, "parts_mode": "no_arp"},
        {"name": "Chorus",   "section_type": "chorus",  "bars": 8, "parts_mode": "full", "chorus_key": True},
        {"name": "Verse 2",  "section_type": "verse",   "bars": 8, "parts_mode": "no_arp"},
        {"name": "Chorus 2", "section_type": "chorus",  "bars": 8, "parts_mode": "full", "chorus_key": True},
        {"name": "Outro",    "section_type": "outro",   "bars": 4, "parts_mode": "chords_only"},
    ],  # 40 bars
    # Minimal — foundation intro builds into full arrangement.
    "minimal": [
        {"name": "Intro",  "section_type": "intro",  "bars": 4,  "parts_mode": "foundation"},
        {"name": "Main",   "section_type": "verse",  "bars": 16, "parts_mode": "full"},
        {"name": "Outro",  "section_type": "outro",  "bars": 4,  "parts_mode": "melodic"},
    ],  # 24 bars
}


def _song_tempo_map(section_results: list[dict], bpm: float,
                    ending_bars: int = 0) -> list[tuple[float, float]]:
    """Tempo map for a built song: subtle chorus push + final ritardando.

    Choruses run ~1.2% faster than the base tempo — enough to feel lifted
    without reading as a tempo change — and drop back at the next section.
    When an ending bar is appended, the last bar slows in four steps so the
    final chord lands with weight. Returns (beat, bpm) points for the MIDI
    tempo track; deterministic, so regeneration reproduces it exactly.
    """
    points: list[tuple[float, float]] = [(0.0, float(bpm))]
    in_push = False
    for sec in section_results:
        start_beat = float(sec["start_bar"] * 4)
        is_chorus = sec["section_type"] in ("chorus", "post_chorus")
        if is_chorus and not in_push:
            points.append((start_beat, bpm * 1.012))
            in_push = True
        elif not is_chorus and in_push:
            points.append((start_beat, float(bpm)))
            in_push = False
    if ending_bars > 0 and section_results:
        last = section_results[-1]
        end_start = float((last["start_bar"] + last["bars"]) * 4)
        # last["bars"] already includes any ending bar appended by the caller;
        # the ritardando covers the final `ending_bars` bars.
        rit_start = end_start - ending_bars * 4
        for i, factor in enumerate((0.96, 0.90, 0.84, 0.76)):
            points.append((rit_start + i * (ending_bars * 4) / 4.0, bpm * factor))
    return points
