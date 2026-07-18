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
import random

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

    Uses crc32, NOT the built-in hash(): string hashing is salted per process
    (PYTHONHASHSEED), so hash()-derived seeds silently broke seed replay across
    app restarts — the same seed produced different music after a relaunch.
    """
    import zlib
    return zlib.crc32(f"{main_seed}:{section_idx}:{part}".encode()) % (2 ** 31)


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


def apply_arrangement_dynamics(song_events: dict[str, list],
                               section_results: list[dict],
                               base_seed: int) -> None:
    """Classic arrangement dropouts, applied in place to the assembled song.

    Real records breathe: instruments drop out so others lead. Section
    part-modes already vary WHICH parts exist per section, but once a part
    entered it used to run unbroken to the outro. This pass adds the classic
    devices, chosen per-song from a seeded RNG so every regeneration flow
    (which replays the same base_seed) reproduces the exact same arrangement:

      drop         — the last 2 beats before a chorus go silent in the rhythm
                     section (drums always, bass half the time, and sometimes
                     the FULL band stops with only the melody carrying across),
                     so the chorus slams back in ("suck the air out, then hit").
      breakdown    — drums sit out the first half of a bridge; sometimes the
                     bass sits out with them (melody + chords fully alone),
                     and the rhythm section re-enters at the halfway point.
      thinned v2   — the second verse opens with kick and hats only for a few
                     bars (no snare/claps/cymbals); half the time the chords
                     sit out too — the classic stripped restart.
      late entry   — the FIRST verse opens with just the groove for a few
                     bars before the melody arrives.
      arp growth   — the first chorus carries its arpeggio only in the second
                     half, so the final chorus (full arp + counter-melody)
                     reads bigger than the ones before it.

    Probabilities are below 1 so songs differ — some get several devices,
    some none. RNG draws never depend on song_events contents, only on the
    section list, so the same seed always yields the same strip windows.
    Runs BEFORE the ending bar is appended, so the final cadence is never
    stripped.
    """
    rng = random.Random(_part_seed(base_seed, 911, "dynamics"))
    # Kick + closed/open hats survive verse-2 thinning (GM pitches)
    _KICK_HATS = {35, 36, 42, 44, 46}

    def _strip(part: str, lo: float, hi: float, keep: set | None = None) -> None:
        evs = song_events.get(part)
        if not evs:
            return
        song_events[part] = [
            e for e in evs
            if not (lo <= e.start < hi) or (keep is not None and e.pitch in keep)
        ]

    n_choruses = sum(1 for s in section_results if s.get("section_type") == "chorus")
    verse_occurrence = 0
    chorus_occurrence = 0
    for sec in section_results:
        stype = sec.get("section_type")
        start_beat = sec.get("start_bar", 0) * 4.0
        bars = sec.get("bars", 0)

        if stype == "chorus":
            chorus_occurrence += 1
            _dropped = False
            # (When the drop fires it REPLACES any boundary drum fill living in
            # the same two beats — fill or drop, never both, by construction.)
            if start_beat >= 8.0 and rng.random() < 0.6:
                _dropped = True
                _strip("drums", start_beat - 2.0, start_beat)
                if rng.random() < 0.5:
                    _strip("bass", start_beat - 2.0, start_beat)
                    # Full-band stop: everything but the melody cuts — the most
                    # "rehearsed" moment an arrangement can have. Only when the
                    # bass already dropped, so the stop is all-or-nothing.
                    if rng.random() < 0.5:
                        _strip("chords", start_beat - 2.0, start_beat)
                        _strip("pads", start_beat - 2.0, start_beat)
                        _strip("arpeggio", start_beat - 2.0, start_beat)
            # Snare-roll build into the FINAL chorus: a 16th-note roll swelling
            # through the last 3 beats — the drop's opposite ("fill the air,
            # then hit"), so the two are mutually exclusive.
            _roll = rng.random()
            if (chorus_occurrence == n_choruses and n_choruses > 1 and not _dropped
                    and start_beat >= 16.0 and _roll < 0.5 and song_events.get("drums")):
                t = start_beat - 3.0
                while t < start_beat - 0.2:
                    vel = int(50 + (t - (start_beat - 3.0)) / 2.8 * 60)
                    song_events["drums"].append(NoteEvent(38, t, 0.12, min(115, vel), 9))
                    t += 0.25
                song_events["drums"].sort(key=lambda e: e.start)
            # Breakdown final chorus (the modern double-chorus): the final
            # chorus opens half-stripped — melody over a thinned kit — and the
            # full band returns at the midpoint, making the back half enormous.
            _breakdown_roll = rng.random()
            if (chorus_occurrence == n_choruses and n_choruses > 1 and bars >= 8
                    and _breakdown_roll < 0.3):
                half = start_beat + (bars // 2) * 4.0
                _strip("chords", start_beat, half)
                _strip("pads", start_beat, half)
                _strip("arpeggio", start_beat, half)
                _strip("bass", start_beat, half)
                _strip("drums", start_beat, half, keep=_KICK_HATS | {39})
            # Arp growth: only when a LATER chorus exists to be the bigger one
            if chorus_occurrence == 1 and n_choruses > 1 and bars >= 4 and rng.random() < 0.5:
                _strip("arpeggio", start_beat, start_beat + (bars // 2) * 4.0)

        elif stype == "bridge" and bars >= 4 and rng.random() < 0.75:
            _strip("drums", start_beat, start_beat + (bars // 2) * 4.0)
            if rng.random() < 0.4:
                _strip("bass", start_beat, start_beat + (bars // 2) * 4.0)

        elif stype == "verse":
            verse_occurrence += 1
            if verse_occurrence == 1 and bars >= 4 and rng.random() < 0.5:
                # A late vocal entrance only works over a groove-only lead-in. If
                # the intro already carried a melody (its own line or the chorus
                # hook tease), stripping the verse's opening bars turns one clean
                # entrance into melody -> silence -> melody, which reads as the
                # melody dropping out. Only earn the late entry when nothing
                # melodic preceded this first verse.
                intro_had_melody = any(e.start < start_beat - 0.5
                                       for e in song_events.get("melody", []))
                if not intro_had_melody:
                    entry_bars = min(4, max(2, bars // 4))
                    _strip("melody", start_beat, start_beat + entry_bars * 4.0)
            elif verse_occurrence == 2 and rng.random() < 0.5:
                thin_bars = min(4, max(2, bars // 4))
                _strip("drums", start_beat, start_beat + thin_bars * 4.0, keep=_KICK_HATS)
                if rng.random() < 0.5:
                    _strip("chords", start_beat, start_beat + thin_bars * 4.0)


def apply_melodic_pickups(song_events: dict[str, list],
                          section_results: list[dict],
                          base_seed: int,
                          scale: str,
                          style: dict) -> None:
    """Melodic pickups (anacrusis) into sections, applied in place.

    The classic "and-4-and | ONE": a short stepwise run in the last beats of
    one section that LEADS into the next section's first melody note, so the
    boundary is sung across instead of merely arriving. Choruses get pickups
    most often; verses and bridges sometimes; outros never.

    Must run AFTER apply_arrangement_dynamics so pickups target melody that
    actually survived the dropouts — and a pickup sounding through a full-band
    stop (melody alone leading the chorus back in) is exactly the classic move.
    Seeded from base_seed so regeneration flows reproduce the same pickups.
    """
    from app.theory.scales import build_scale
    from app.core.instruments import instrumentation_for

    melody = song_events.get("melody")
    if not melody:
        return

    rng = random.Random(_part_seed(base_seed, 913, "pickups"))
    mel_scale = style.get("melody_scale", scale)
    profile = instrumentation_for(style).get("melody")
    _PICKUP_PROB = {"chorus": 0.55, "verse": 0.3, "bridge": 0.3}

    added: list = []
    for sec in section_results:
        prob = _PICKUP_PROB.get(sec.get("section_type"), 0.0)
        boundary = sec.get("start_bar", 0) * 4.0
        # RNG draws must not depend on event content — draw first, always.
        roll = rng.random()
        n_notes = rng.choice([2, 3])
        from_below = rng.random() < 0.7
        if prob == 0.0 or boundary < 4.0 or roll >= prob:
            continue

        # The target: the section's first melody note, on or just after its downbeat
        target = min((e for e in melody if boundary - 0.05 <= e.start < boundary + 1.0),
                     key=lambda e: e.start, default=None)
        if target is None:
            continue

        # The runway: the pickup window must be melody-free (don't collide with
        # a held cadence note ringing across the boundary)
        span = n_notes * 0.5
        window_start = boundary - span - 0.1
        if any(e.start < boundary and e.start + e.duration > window_start for e in melody
               if e is not target):
            continue

        # Stepwise run through the section's OWN key (chorus lifts change keys)
        sec_key = sec.get("key") or "C"
        try:
            lattice = build_scale(sec_key, mel_scale, octave_start=2, num_octaves=6)
        except ValueError:
            continue
        t_idx = min(range(len(lattice)), key=lambda i: abs(lattice[i] - target.pitch))
        step_dir = 1 if from_below else -1
        pitches = [lattice[max(0, min(len(lattice) - 1, t_idx - step_dir * k))]
                   for k in range(n_notes, 0, -1)]
        # A pickup outside the melody instrument's range would be unplayable —
        # skip the device rather than bend the line.
        if profile and any(not (profile["range"][0] <= p <= profile["range"][1]) for p in pitches):
            continue

        for k, pitch in enumerate(pitches):
            start = boundary - (n_notes - k) * 0.5
            added.append(type(target)(
                pitch=pitch, start=start, duration=0.42,
                velocity=max(30, min(127, target.velocity - 14 + k * 5)),
                channel=target.channel,
            ))

    if added:
        song_events["melody"] = sorted(melody + added, key=lambda e: e.start)


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
        stype = sec["section_type"]
        is_chorus = stype in ("chorus", "post_chorus")
        if stype == "pre_chorus" and not in_push:
            # Micro-accel through the build: half the chorus push, so the
            # pre-chorus leans forward and the chorus completes the lift.
            points.append((start_beat, bpm * 1.006))
        if is_chorus and not in_push:
            points.append((start_beat, bpm * 1.012))
            in_push = True
        elif not is_chorus and stype != "pre_chorus" and in_push:
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
