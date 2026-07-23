# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Instrument registry — the single source of truth for instrument identity.

Each style JSON binds its part roles to instruments here via an
``instrumentation`` block (``{"chords": "rhodes_ep", ...}``). Everything
downstream derives from the registry entry: MIDI track names and GM programs
now (Phase 1), playing profiles for the generators (Phase 2), and in-app
playback voices (Phase 3). See docs/instrument-identity-design.md.

Registry fields:
    display_name       what a human calls it — used for MIDI track names and UI labels
    gm_program         General MIDI program number (0-indexed) written to the file
    playback_voice     frontend voice id (sampler or synth family) — consumed in Phase 3
    range              [low, high] playable MIDI note range — consumed in Phase 2
    polyphony          max simultaneous notes the instrument can honestly play — Phase 2
    sustain            "decay" (struck/plucked, note fades on its own),
                       "sustain" (held as long as played: winds, strings, organ, leads),
                       "ring" (rings past release: crash-like pads) — Phase 2
    strum              seconds between voiced notes when playing a chord (0 = block) — Phase 2
    breath             True for wind instruments: phrase gaps, no overlapping notes — Phase 2
    monophonic_legato  True when consecutive notes should slur, never overlap — Phase 2
"""

PART_ROLES = ("chords", "bass", "melody", "arpeggio", "pads", "counter_melody")

# Roles that require polyphony — a monophonic instrument bound to one of these
# is a style-authoring error (validated by tests).
POLYPHONIC_ROLES = ("chords", "pads")


def _inst(display_name: str, gm_program: int, playback_voice: str, range_: tuple[int, int],
          polyphony: int, sustain: str, strum: float = 0.0,
          breath: bool = False, monophonic_legato: bool = False) -> dict:
    return {
        "display_name": display_name, "gm_program": gm_program,
        "playback_voice": playback_voice, "range": list(range_),
        "polyphony": polyphony, "sustain": sustain, "strum": strum,
        "breath": breath, "monophonic_legato": monophonic_legato,
    }


INSTRUMENTS: dict[str, dict] = {
    # ── Keys ──────────────────────────────────────────────────────────────────
    "rhodes_ep":      _inst("Rhodes EP",       4,  "electric_piano_1", (28, 96), 8, "decay", strum=0.008),
    "wurlitzer_ep":   _inst("Wurlitzer EP",    5,  "electric_piano_2", (28, 96), 8, "decay", strum=0.008),
    "clavinet":       _inst("Clavinet",        7,  "clavinet",         (36, 88), 4, "decay"),
    "drawbar_organ":  _inst("Drawbar Organ",   16, "drawbar_organ",    (36, 96), 8, "sustain"),
    "rock_organ":     _inst("Rock Organ",      18, "drawbar_organ",    (36, 96), 8, "sustain"),
    "accordion":      _inst("Accordion",       23, "accordion",        (41, 91), 6, "sustain"),
    # ── Mallets ───────────────────────────────────────────────────────────────
    "vibraphone":     _inst("Vibraphone",      11, "vibraphone",       (53, 89), 4, "ring"),
    # playback_voice is vibraphone (nearest sampled mallet): the exported MIDI keeps
    # GM 12 (Marimba), but in-app preview plays real vibes instead of a generic pluck.
    "marimba":        _inst("Marimba",         12, "vibraphone",       (45, 96), 4, "decay"),
    # ── Guitars ───────────────────────────────────────────────────────────────
    "nylon_guitar":   _inst("Nylon Guitar",    24, "acoustic_guitar_nylon", (40, 83), 6, "decay", strum=0.018),
    "steel_guitar":   _inst("Steel Guitar",    25, "acoustic_guitar_nylon", (40, 84), 6, "decay", strum=0.018),
    "jazz_guitar":    _inst("Jazz Guitar",     26, "acoustic_guitar_nylon", (40, 84), 6, "decay", strum=0.015),
    "clean_electric_guitar": _inst("Clean Electric Guitar", 27, "acoustic_guitar_nylon", (40, 86), 6, "decay", strum=0.012),
    # Distorted guitars sustain like a held synth, not a plucked string, and
    # honest polyphony is low: distortion turns dense voicings into mud, which
    # is why rock/metal styles pair these with power_chords (root+5 dyads).
    "overdriven_guitar":  _inst("Overdriven Guitar", 29, "synth_lead", (35, 86), 4, "sustain", strum=0.008),
    "distortion_guitar":  _inst("Distortion Guitar", 30, "synth_lead", (35, 86), 4, "sustain", strum=0.006),
    # ── Basses ────────────────────────────────────────────────────────────────
    # playback_voice names the exact in-app bass sample set (frontend/public/samples/bass/*),
    # decoupled from gm_program so preview and MIDI agree on the instrument.
    "upright_bass":   _inst("Upright Bass",    32, "acoustic_bass",       (28, 60), 1, "decay", monophonic_legato=True),
    "electric_bass":  _inst("Electric Bass",   33, "electric_bass_finger", (28, 62), 1, "decay", monophonic_legato=True),
    "picked_bass":    _inst("Picked Bass",     34, "electric_bass_pick",  (28, 62), 1, "decay", monophonic_legato=True),
    "fretless_bass":  _inst("Fretless Bass",   35, "fretless_bass",       (28, 62), 1, "decay", monophonic_legato=True),
    "slap_bass":      _inst("Slap Bass",       36, "slap_bass_1",         (28, 60), 1, "decay", monophonic_legato=True),
    "synth_bass":     _inst("Synth Bass",      38, "synth_bass_1",        (24, 60), 1, "sustain", monophonic_legato=True),
    "sub_808":        _inst("808 Sub",         38, "synth_bass_1",        (24, 55), 1, "sustain", monophonic_legato=True),
    "contrabass":     _inst("Contrabass",      43, "acoustic_bass",       (28, 60), 1, "sustain", monophonic_legato=True),
    # ── Orchestral ────────────────────────────────────────────────────────────
    "string_ensemble": _inst("String Ensemble", 48, "string_ensemble_1", (36, 96), 12, "sustain"),
    "tremolo_strings": _inst("Tremolo Strings", 44, "string_ensemble_1", (36, 96), 12, "sustain"),
    "trumpet":        _inst("Trumpet",         56, "melody_lead",      (54, 86), 1, "sustain", breath=True, monophonic_legato=True),
    "french_horn":    _inst("French Horn",     60, "melody_lead",      (41, 77), 1, "sustain", breath=True, monophonic_legato=True),
    "brass_section":  _inst("Brass Section",   61, "string_ensemble_1", (40, 84), 6, "sustain"),
    # ── Winds ─────────────────────────────────────────────────────────────────
    "alto_sax":       _inst("Alto Sax",        65, "melody_lead",      (49, 81), 1, "sustain", breath=True, monophonic_legato=True),
    "tenor_sax":      _inst("Tenor Sax",       66, "melody_lead",      (44, 76), 1, "sustain", breath=True, monophonic_legato=True),
    "oboe":           _inst("Oboe",            68, "melody_lead",      (58, 91), 1, "sustain", breath=True, monophonic_legato=True),
    "flute":          _inst("Flute",           73, "melody_lead",      (60, 96), 1, "sustain", breath=True, monophonic_legato=True),
    # ── Synth leads ───────────────────────────────────────────────────────────
    "square_lead":    _inst("Square Lead",     80, "synth_lead",       (48, 96), 2, "sustain"),
    "saw_lead":       _inst("Saw Lead",        81, "synth_lead",       (48, 96), 2, "sustain"),
    "charang_lead":   _inst("Charang Lead",    84, "synth_lead",       (48, 96), 2, "sustain"),
    "vox_lead":       _inst("Vox Lead",        85, "synth_lead",       (48, 91), 2, "sustain"),
    # ── Synth pads ────────────────────────────────────────────────────────────
    "newage_pad":     _inst("New Age Pad",     88, "pad_synth",        (36, 96), 12, "ring"),
    "warm_pad":       _inst("Warm Pad",        89, "pad_synth",        (36, 96), 12, "ring"),
    "polysynth_pad":  _inst("Polysynth Pad",   90, "pad_synth",        (36, 96), 12, "sustain"),
    "choir_pad":      _inst("Choir Pad",       91, "pad_synth",        (36, 96), 12, "sustain"),
    "bowed_pad":      _inst("Bowed Pad",       92, "pad_synth",        (36, 96), 12, "sustain"),
    "metallic_pad":   _inst("Metallic Pad",    93, "pad_synth",        (36, 96), 12, "ring"),
    "halo_pad":       _inst("Halo Pad",        94, "pad_synth",        (36, 96), 12, "ring"),
    "sweep_pad":      _inst("Sweep Pad",       95, "pad_synth",        (36, 96), 12, "sustain"),
}


def get_instrument(instrument_id: str) -> dict | None:
    return INSTRUMENTS.get(instrument_id)


def instrumentation_for(style: dict) -> dict[str, dict]:
    """Resolve a style's ``instrumentation`` block → {part: instrument entry}.

    Unknown instrument ids are skipped (the consumer falls back to legacy
    behavior for that part), so a typo in a custom style degrades gracefully
    instead of crashing generation."""
    out: dict[str, dict] = {}
    for part, inst_id in (style.get("instrumentation") or {}).items():
        inst = INSTRUMENTS.get(inst_id)
        if inst is not None:
            out[part] = inst
    return out


def track_display_name(style: dict, part: str) -> str | None:
    """Instrument-based MIDI track name for a part, e.g. "Alto Sax (melody)".

    The role stays in the name so humans can still see what the track is FOR;
    tooling must identify parts by MIDI channel, never by name. Returns None
    when the style doesn't bind this part (caller keeps the plain part name)."""
    inst = instrumentation_for(style).get(part)
    if inst is None:
        return None
    return f"{inst['display_name']} ({part})"


def gm_programs_for(style: dict) -> dict[str, int]:
    """{part: GM program} for every part the style's instrumentation binds."""
    return {part: inst["gm_program"] for part, inst in instrumentation_for(style).items()}


def clamp_range(style_range, inst_range) -> list[int]:
    """Intersect a style's taste range with the instrument's PHYSICAL range.

    The style range says where the part should sit musically; the instrument
    range says what the instrument can play at all — the intersection honors
    both. Falls back to the style range when they don't overlap (bad data
    beats an empty range)."""
    lo = max(style_range[0], inst_range[0])
    hi = min(style_range[1], inst_range[1])
    return [lo, hi] if lo < hi else list(style_range)
