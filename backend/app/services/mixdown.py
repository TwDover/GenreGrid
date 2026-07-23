# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Per-part mixdown policy: GM programs, channels, pan/reverb sends, velocity
balance, and the CC/pitch-bend expression generators applied to finished parts.

Split out of routes_generate.py so mixing concerns live apart from the HTTP
endpoints and arrangement planning (see app/core/arrangement.py).
"""
from app.services.midi_writer import NoteEvent, ControlEvent, PitchBendEvent


# Fallback GM program per part, for user-authored custom styles that ship no
# instrumentation block. Built-in styles derive their programs from the registry
# (app/core/instruments.py) via gm_programs_for — see part_midi_meta.
# GM ref (0-indexed): 0=Grand Piano, 4=EP1(Rhodes), 5=EP2(Chorus EP), 7=Clavinet,
#   11=Vibraphone, 12=Marimba, 16=Drawbar Organ, 18=Rock Organ,
#   24=Nylon Guitar, 25=Steel Guitar, 26=Jazz Guitar, 27=Clean Electric Guitar,
#   32=Acoustic Bass, 33=Elec Bass(finger), 35=Fretless Bass, 38=Synth Bass 1,
#   43=Contrabass, 44=Tremolo Strings, 48=String Ensemble 1, 56=Trumpet,
#   60=French Horn, 61=Brass Section, 65=Alto Sax, 66=Tenor Sax, 68=Oboe, 73=Flute,
#   80=Lead Square, 81=Lead Saw, 84=Lead Charang, 85=Lead Voice,
#   88=Pad New Age, 89=Pad Warm, 90=Pad Polysynth, 91=Pad Choir,
#   92=Pad Bowed, 93=Pad Metallic, 94=Pad Halo, 95=Pad Sweep
_DEFAULT_PROGRAMS: dict[str, int] = {
    "chords":   4,   # EP 1 (Rhodes) — warmer fallback; avoids three parts sharing grand piano
    "bass":     33,  # Electric Bass (finger)
    "melody":   73,  # Flute — cuts above chord register without fighting EP
    "arpeggio": 11,  # Vibraphone — distinct attack; doesn't blur into pad/piano textures
    "pads":     89,  # Pad Warm — sustained glue layer above the comp
    "counter_melody": 48,  # String Ensemble — backing harmony line under the lead
}
_VELOCITY_DROP = 20  # notes quieter than this are inaudible — discard them


# Per-part velocity scale factors. Bass sits loudest, chords slightly back,
# melody present above chords, arpeggio light. Drums are not scaled.
_VELOCITY_SCALE: dict[str, float] = {
    "bass":     0.88,
    "chords":   0.68,
    "melody":   1.00,
    "arpeggio": 0.62,
    "pads":     0.52,
    "counter_melody": 0.82,
}


_PART_PAN = {"bass": 64, "chords": 46, "melody": 80, "arpeggio": 76, "pads": 40, "counter_melody": 92}
_PART_CHANNELS = {"chords": 0, "bass": 1, "melody": 2, "arpeggio": 3, "pads": 4, "counter_melody": 5}


def part_midi_meta(style: dict) -> tuple[dict[str, int], dict[str, str]]:
    """(GM programs, MIDI track names) per part for a style.

    Instrumentation-first: parts bound in the style's ``instrumentation`` block
    take their program and display name from the instrument registry (the
    single source of truth — see docs/instrument-identity-design.md). Every
    built-in style binds all six roles, so the registry fully determines their
    programs; ``_DEFAULT_PROGRAMS`` only fills in for user-authored custom styles
    that ship no instrumentation block.
    """
    from app.core.instruments import gm_programs_for, track_display_name

    programs = {**_DEFAULT_PROGRAMS}
    programs.update(gm_programs_for(style))
    track_names = {}
    for part in _PART_CHANNELS:
        name = track_display_name(style, part)
        if name:
            track_names[part] = name
    return programs, track_names

# Comp styles that use short articulated hits — sustain pedal would blur their
# intended staccato character. Styles with chord_rhythm also get the same treatment
# because their note durations are computed to fill to the next hit, and sustain
# would smear across those carefully-timed arrivals.
_NO_SUSTAIN_COMP_STYLES = frozenset({
    "jazz_comp", "bossa_comp", "funk_stab", "house_stab", "synth_gate",
    # Distorted-guitar comps: pedal smear across power-chord changes is mud
    "rock_drive", "palm_mute", "doom_crush",
})
# Styles whose chord instruments (strings, brass) already sustain naturally —
# adding CC64 causes unintended smear across bar lines.
_NO_SUSTAIN_STYLE_IDS = frozenset({"epic_orchestral"})

# CC91 reverb send per part: bass dry/upfront, arpeggio spacious/behind.
# Creates a front-to-back depth gradient that separates parts spatially.
_PART_REVERB = {"bass": 12, "chords": 28, "melody": 48, "arpeggio": 58, "pads": 66, "counter_melody": 52}

# Per-style reverb overrides — atmospheric/cinematic styles need more room.
# Parts not listed fall back to _PART_REVERB.
_STYLE_REVERB: dict[str, dict[str, int]] = {
    "cinematic":       {"chords": 55, "melody": 72, "arpeggio": 68},
    "epic_orchestral": {"chords": 62, "melody": 78, "arpeggio": 72},
    "ambient":         {"chords": 72, "melody": 85, "arpeggio": 78},
    "dark_ambient":    {"chords": 75, "melody": 82, "arpeggio": 82},
    "cloud_rap":       {"chords": 62, "melody": 70, "arpeggio": 68},
    "trap_soul":       {"chords": 52, "melody": 62, "arpeggio": 65},
    "lofi":            {"chords": 42, "melody": 50, "arpeggio": 55},
    "jazz":            {"chords": 32, "melody": 40, "arpeggio": 45},
    "synthwave":       {"chords": 48, "melody": 58, "arpeggio": 65},
    "future_bass":     {"chords": 55, "melody": 65, "arpeggio": 70},
    "drum_and_bass":   {"chords": 35, "melody": 45, "arpeggio": 50},
}

# Styles where arpeggio is the primary melodic texture (no explicit melody, or
# melody is a pad). Raise the arpeggio scale factor so it isn't buried behind chords.
_STYLE_ARPEGGIO_VEL: dict[str, float] = {
    "ambient":      0.82,
    "dark_ambient": 0.78,
    "cloud_rap":    0.80,
    "trap_soul":    0.78,
    "lofi":         0.75,
    "cinematic":    0.75,
    "synthwave":    0.72,
    "future_bass":  0.75,
    "dark_trap":    0.72,
}


def _generate_part_cc(part: str, total_bars: int, channel: int, style: dict | None = None) -> list[ControlEvent]:
    """Generate pan (CC10), reverb (CC91), and sustain pedal (CC64) for chords.

    Sustain is only applied for styles that use long-hold voicings (pads, ambient,
    cinematic). Short-articulation styles (jazz_comp, funk_stab, etc.) and any style
    with a step-based chord_rhythm skip it — sustain would blur their intentional
    staccato character.
    """
    cc: list[ControlEvent] = []
    cc.append(ControlEvent(control=10, value=_PART_PAN.get(part, 64), start=0.0, channel=channel))
    s = style or {}
    style_id = s.get("id", "")
    reverb = _STYLE_REVERB.get(style_id, {}).get(part, _PART_REVERB.get(part))
    if reverb is not None:
        cc.append(ControlEvent(control=91, value=reverb, start=0.0, channel=channel))
    if part == "chords":
        comp = s.get("comp_style", "")
        use_sustain = (comp not in _NO_SUSTAIN_COMP_STYLES
                       and not s.get("chord_rhythm")
                       and style_id not in _NO_SUSTAIN_STYLE_IDS)
        if use_sustain:
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


def _generate_bass_expression_cc(events: list[NoteEvent], channel: int) -> list[ControlEvent]:
    """CC11 expression for bass — natural attack swell, settled sustain.

    Gives walking and standard bass lines the feel of a bowed or plucked
    instrument where the note blooms slightly after the attack. Skipped for
    808 bass (which uses pitch bend instead and is already very expressive).
    """
    cc: list[ControlEvent] = []
    for note in sorted(events, key=lambda e: e.start):
        d = note.duration
        if d <= 0.3:
            cc.append(ControlEvent(control=11, value=108, start=note.start, channel=channel))
        else:
            cc.append(ControlEvent(control=11, value=82,  start=note.start,            channel=channel))
            cc.append(ControlEvent(control=11, value=112, start=note.start + 0.07,     channel=channel))
            cc.append(ControlEvent(control=11, value=92,  start=note.start + d * 0.40, channel=channel))
            cc.append(ControlEvent(control=11, value=82,  start=note.start + d * 0.88, channel=channel))
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


# ── Section-level automation ─────────────────────────────────────────────────
# Pre-chorus builds: a rising CC74 filter sweep (with CC1 mod wheel at half
# depth) and a CC11 crescendo into the chorus. Both ramp in _AUTOMATION_STEPS
# discrete steps — coarse enough to keep the event count tiny, fine enough that
# a synth's filter glides rather than jumps.
_AUTOMATION_STEPS = 8
_SWEEP_PARTS = ("chords", "pads")            # the sustained textures a sweep reads on
_SWEEP_CC74_LO, _SWEEP_CC74_HI = 40, 110
_CC74_NEUTRAL = 84                           # post-sweep reset — a neutral default cutoff
_CRESC_PARTS = ("chords", "pads", "arpeggio")  # melody excluded: it has note-level CC11 swells
_CRESC_CC11_LO, _CRESC_CC11_HI = 70, 118
_CC11_NEUTRAL = 100


def _ramp_times(start: float, span_beats: float) -> list[tuple[float, float]]:
    """(time, fraction 0..1) pairs for a linear ramp across a section — first
    point on the downbeat, last on the section's final beat."""
    last = max(1.0, span_beats - 1.0)
    return [(start + (i / (_AUTOMATION_STEPS - 1)) * last, i / (_AUTOMATION_STEPS - 1))
            for i in range(_AUTOMATION_STEPS)]


def generate_build_sweeps(section_results: list[dict], parts: list[str]) -> dict[str, list[ControlEvent]]:
    """Rising CC74 (filter cutoff) sweep across every pre-chorus — the classic
    electronic build — plus the same shape on CC1 (mod wheel) at half depth for
    synths that map CC1 to intensity instead. Both reset to neutral at the next
    section's downbeat so the chorus doesn't inherit a wide-open filter.
    """
    targets = [p for p in _SWEEP_PARTS if p in parts]
    out: dict[str, list[ControlEvent]] = {}
    if not targets:
        return out
    for i, sec in enumerate(section_results):
        if sec.get("section_type") != "pre_chorus":
            continue
        start = float(sec["start_bar"] * 4)
        span = sec["bars"] * 4.0
        reset_beat = (float(section_results[i + 1]["start_bar"] * 4)
                      if i + 1 < len(section_results) else start + span)
        for part in targets:
            ch = _PART_CHANNELS[part]
            evs = out.setdefault(part, [])
            for t, frac in _ramp_times(start, span):
                v = round(_SWEEP_CC74_LO + frac * (_SWEEP_CC74_HI - _SWEEP_CC74_LO))
                evs.append(ControlEvent(control=74, value=v, start=t, channel=ch))
                evs.append(ControlEvent(control=1, value=v // 2, start=t, channel=ch))
            evs.append(ControlEvent(control=74, value=_CC74_NEUTRAL, start=reset_beat, channel=ch))
            evs.append(ControlEvent(control=1, value=_CC74_NEUTRAL // 2, start=reset_beat, channel=ch))
    return out


def generate_section_crescendo(section_results: list[dict], parts: list[str]) -> dict[str, list[ControlEvent]]:
    """CC11 (expression) crescendo across every pre-chorus that resolves into a
    chorus, resetting at the chorus downbeat. Melody is deliberately excluded —
    _generate_melody_expression_cc already writes note-level CC11 swells there,
    and a section ramp on the same controller would fight them.
    """
    targets = [p for p in _CRESC_PARTS if p in parts]
    out: dict[str, list[ControlEvent]] = {}
    if not targets:
        return out
    for sec, nxt in zip(section_results, section_results[1:]):
        if sec.get("section_type") != "pre_chorus" or nxt.get("section_type") != "chorus":
            continue
        start = float(sec["start_bar"] * 4)
        span = sec["bars"] * 4.0
        chorus_beat = float(nxt["start_bar"] * 4)
        for part in targets:
            ch = _PART_CHANNELS[part]
            evs = out.setdefault(part, [])
            for t, frac in _ramp_times(start, span):
                v = round(_CRESC_CC11_LO + frac * (_CRESC_CC11_HI - _CRESC_CC11_LO))
                evs.append(ControlEvent(control=11, value=v, start=t, channel=ch))
            evs.append(ControlEvent(control=11, value=_CC11_NEUTRAL, start=chorus_beat, channel=ch))
    return out


def _drop_quiet(events: list[NoteEvent]) -> list[NoteEvent]:
    return [e for e in events if e.velocity >= _VELOCITY_DROP]


def _scale_velocity(events: list[NoteEvent], part: str, style_id: str = "") -> list[NoteEvent]:
    if part == "arpeggio" and style_id in _STYLE_ARPEGGIO_VEL:
        factor = _STYLE_ARPEGGIO_VEL[style_id]
    else:
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
