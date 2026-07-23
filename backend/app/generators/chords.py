# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
import random
from typing import List

from app.services.midi_writer import NoteEvent
from app.theory.chords import roman_to_chord
from app.services.variation import should_trigger
from app.services.humanize import timing_jitter, phrase_breath_factor, style_jitter
from app.theory.rhythm import apply_swing
from app.core.instruments import instrumentation_for, clamp_range


def _render_riff_guitar(
    style: dict, key: str, scale: str, bars: int, progression: list,
    section_type: str | None, ch_low: int, ch_high: int,
    velocity_base: int, vel_arc_start: float, swing_amount: float, strum_speed: float,
) -> List[NoteEvent]:
    """Render the song's riff (app.generators.riff) as a distorted guitar part:
    power-chord stabs (root+5th, +octave when it fits) on the figure's accents,
    single-note palm-muted chugs elsewhere. Approach notes stay single notes."""
    from app.generators.riff import build_riff
    from app.theory.rhythm import apply_swing as _apply_swing

    ticks_per_beat = 480

    def _swing(beat: float) -> float:
        if swing_amount < 0.01:
            return beat
        tick = int(beat * ticks_per_beat)
        return _apply_swing(tick, swing_amount, ticks_per_beat) / ticks_per_beat

    riff = build_riff(style, key, scale, progression, bars, section_type, pedal_low=ch_low)
    events: List[NoteEvent] = []
    for rn in riff:
        bar_num = int(rn.start / 4.0)
        t = bar_num / max(1, bars - 1)
        base = int(velocity_base * (vel_arc_start + (1.0 - vel_arc_start) * t))
        base = int(base * phrase_breath_factor(bar_num))
        # Stabs punch above the chugs; the wrist accents the figure.
        vel = base + (10 if rn.accent else -6) + random.randint(-4, 4)

        if rn.accent and not rn.approach:
            voices = [rn.pitch, rn.pitch + 7]
            if rn.pitch + 12 <= ch_high:
                voices.append(rn.pitch + 12)
        else:
            voices = [rn.pitch]

        start = max(0.0, _swing(rn.start) + timing_jitter(style_jitter(style)))
        for vi, p in enumerate(voices):
            events.append(NoteEvent(
                pitch=min(127, max(0, p)),
                start=max(0.0, start + vi * strum_speed),
                duration=rn.duration,
                velocity=max(1, min(127, vel - vi * 3)),
                channel=0,
            ))
    return events


def _apply_inversion(pitches: list[int], inversion: int) -> list[int]:
    result = sorted(pitches)
    for _ in range(inversion % max(1, len(result))):
        result = sorted(result[1:] + [result[0] + 12])
    return result


def _movement_score(pitches: list[int], prev_pitches: list[int]) -> float:
    """Sum of each new pitch's distance to its nearest previous pitch."""
    return sum(min(abs(p - q) for q in prev_pitches) for p in pitches)


def _voice_lead(pitches: list[int], prev_pitches: list[int]) -> list[int]:
    """Return the inversion of pitches that minimizes total movement from prev_pitches.

    Uses a 2-key score: (total_movement, -shared_pitch_classes). When two voicings
    cost equal movement, the one retaining more common tones (guide tones) wins.
    """
    if not prev_pitches:
        return sorted(pitches)

    prev_pcs = {q % 12 for q in prev_pitches}

    def _score(candidate: list[int]) -> tuple[float, int]:
        move_cost = _movement_score(candidate, prev_pitches)
        common = sum(1 for p in candidate if p % 12 in prev_pcs)
        return (move_cost, -common)  # minimize movement, maximize common pitch classes

    best = sorted(pitches)
    best_score = _score(best)

    for inv in range(len(pitches)):
        candidate = _apply_inversion(pitches, inv)
        for top_shift in (0, 12, -12):
            variant = candidate[:-1] + [candidate[-1] + top_shift]
            s = _score(variant)
            if s < best_score:
                best = variant
                best_score = s

    return best


def _clamp_register(pitches: list[int], low: int = 55, high: int = 84) -> list[int]:
    """Shift the entire voicing by octaves until it fits within [low, high].

    If the voicing spans more than the range (too wide to fit), nudge individual
    notes that fall below the floor up by an octave so the lowest note is never
    below `low`, even if the top note exceeds `high`.
    """
    s = sorted(pitches)
    while s[0] < low and s[-1] + 12 <= 127:
        s = [p + 12 for p in s]
    while s[-1] > high and s[0] - 12 >= 0:
        s = [p - 12 for p in s]
    # Fallback: voicing too wide to fit entirely — shift individual sub-floor notes up
    if s[0] < low:
        s = sorted(p + 12 if p < low else p for p in s)
    return s


def _drop_2(pitches: list[int]) -> list[int]:
    """Drop the second-highest note an octave for a more open jazz voicing."""
    if len(pitches) < 4:
        return pitches
    s = sorted(pitches)
    s[-2] -= 12
    return sorted(s)


def _declutter(pitches: list[int], core_pcs: set[int], low: int, high: int) -> list[int]:
    """Open internal semitone clusters so the chord reads as a clear chord.

    Voice-leading inverts an extended chord to minimise movement, which can drag
    a tension (typically the 9th) down a semitone from a core tone in the SAME
    octave — a Cm9 collapses into a C-D-Eb grind that the ear hears as mud, not
    harmony (measured: ~40% of block-chord voicings had such a cluster). For each
    semitone-adjacent pair, relocate the offending note an octave (harmony-
    preserving — same pitch classes) so the voicing spreads; when the register is
    too tight to spread (chords are capped below the melody), DROP the tension so
    a clean triad/7th remains — the 9th colour still lives in the pads/arp. Core
    tones (root/3rd/5th/7th) are never dropped; a rare all-core crunch (a tight
    maj7) is left alone."""
    ps = sorted(set(pitches))
    for _ in range(2 * len(ps) + 2):
        ci = next((i for i in range(len(ps) - 1) if ps[i + 1] - ps[i] == 1), None)
        if ci is None:
            break
        a, b = ci, ci + 1
        a_core = ps[a] % 12 in core_pcs
        b_core = ps[b] % 12 in core_pcs
        # Relocate the non-core (tension) note; if both are core, the upper one.
        move = b if (a_core and not b_core) else a if (b_core and not a_core) else b
        both_core = a_core and b_core
        up, down = ps[move] + 12, ps[move] - 12
        if up <= high and up not in ps:
            ps[move] = up
        elif down >= low and down not in ps:
            ps[move] = down
        elif not both_core:
            ps.pop(move)            # tension with no room to spread → drop it
        elif len(ps) > 3:
            # An unspreadable both-core semitone is a maj7 root/7th crunch (the
            # only internal semitone triads+7ths produce). Tightly voiced low it
            # reads as mud; drop the 7th (the lower note) for a clean triad — the
            # maj7 colour still lives in the pads. Kept only down to a triad.
            ps.pop(a)
        else:
            break                   # already a triad — accept the crunch
        ps = sorted(ps)
    return ps


def _cap_polyphony(pitches: list[int], max_poly: int | None) -> list[int]:
    """Drop inner voices until the voicing fits the instrument's polyphony.

    Keeps the bass note and the soprano (the two voices that carry the
    harmony); inner color voices go first — the same call an arranger makes
    when a 5-note voicing meets a 4-string instrument."""
    if not max_poly or len(pitches) <= max_poly:
        return pitches
    s = sorted(pitches)
    while len(s) > max_poly:
        del s[len(s) // 2]
    return s


def _voice_vel_offset(note_idx: int, n_notes: int) -> int:
    """Velocity offset per voice for natural piano/keyboard balance.

    Bass note anchors, inner voices recede significantly, soprano note stays
    present. This mimics how a pianist voices a chord: the two outer voices
    carry the harmony while inner voices provide harmonic color without cluttering
    the texture. Replacing the old linear strum taper (which made inner voices
    nearly as loud as the bass) with this model keeps the mix clear.
    """
    if n_notes <= 1:
        return 0
    if note_idx == 0:
        return 8     # bass note: grounded foundation
    if note_idx == n_notes - 1:
        return 2     # soprano note: present but supportive
    return -6        # inner voices: recede to clear space for melody


def _apply_substitution(roman: str, scale: str, complexity: float, secondary_dominants: bool = False, tritone_sub: bool = False) -> str:
    """Probabilistic harmonic color substitutions at higher complexity."""
    if complexity < 0.4 or not should_trigger(0.25):
        return roman
    # Borrow iv from parallel minor when in a major-family scale (darker color)
    if roman == 'IV' and scale in ('major', 'mixolydian', 'lydian', 'pentatonic_major'):
        return 'iv'
    # Raise v to V in minor context: secondary dominant with leading-tone pull
    if roman == 'v' and scale in ('minor', 'dorian', 'phrygian', 'pentatonic_minor'):
        return 'V'
    if secondary_dominants and complexity > 0.45:
        if roman == 'ii' and scale in ('major', 'mixolydian') and should_trigger(0.40):
            return 'II'   # ii → V/V
        if roman == 'vi' and scale in ('major', 'mixolydian') and should_trigger(0.30):
            return 'VI'   # vi → V/ii
        if roman == 'iii' and scale in ('major',) and should_trigger(0.20):
            return 'III'  # iii → V/vi
    # Tritone substitution: V → bII (descends by half-step into I, rich chromatic bass motion)
    if tritone_sub and roman == 'V' and complexity > 0.5 and should_trigger(0.25):
        return 'bII'
    return roman


# Secondary dominants, expressed as the applied-dominant major triad a perfect
# fifth above the target's root (roman_to_chord voices these on any degree). Keyed
# by the target chord that FOLLOWS — placing sec[target] before `target` gives a
# correct V/x → x resolution. Verified: V/ii=VI, V/iii=VII, V/V=II, V/vi=III (maj);
# V/v=II, V/♭VII=IV (min).
_SEC_DOM_MAJOR = {"ii": "VI", "iii": "VII", "V": "II", "vi": "III"}
_SEC_DOM_MINOR = {"v": "II", "V": "II", "bVII": "IV"}
# Borrowed chords (modal interchange) — placed only on weak bars.
_BORROWED_MAJOR = ["iv", "bVII", "bVI"]
_BORROWED_MINOR = ["bII", "bVI"]
_MAJOR_FAMILY = ("major", "mixolydian", "lydian", "pentatonic_major")


def apply_chromatic_color(progression: list, scale: str, prob: float,
                          rng: "random.Random | None" = None) -> list:
    """Season a diatonic progression with at most ONE chromatic color chord per
    4-bar phrase (roadmap-2 item 4). Two devices, resolution-aware:

      * secondary dominant — replace chord *i* with V/x where x = chord *i+1*,
        so the applied dominant actually resolves into the chord it precedes;
      * borrowed chord — modal interchange (iv/♭VII/♭VI in major, ♭II/♭VI in
        minor), only on a weak bar.

    Never touches the final chord (the cadence). ``prob`` 0 → returns the
    progression unchanged (byte-identical); styles opt in via ``chromatic_color``.
    Deterministic given ``rng`` (seed it from the song seed)."""
    if prob <= 0 or len(progression) < 2:
        return list(progression)
    rng = rng or random
    out = list(progression)
    is_major = scale in _MAJOR_FAMILY
    sec = _SEC_DOM_MAJOR if is_major else _SEC_DOM_MINOR
    borrowed = _BORROWED_MAJOR if is_major else _BORROWED_MINOR
    last = len(out) - 1

    for p0 in range(0, len(out), 4):
        idxs = list(range(p0, min(p0 + 4, len(out))))
        if len(idxs) < 2 or rng.random() >= prob:
            continue
        # Prefer a secondary dominant that resolves into the chord that follows.
        # Keep i+1 inside this phrase (idxs[:-1]) so a later phrase can't overwrite
        # the chord an applied dominant was chosen to resolve into.
        cands = [i for i in idxs[:-1] if i != last]
        rng.shuffle(cands)
        placed = False
        for i in cands:
            target = out[i + 1]
            repl = sec.get(target)
            if repl and out[i] != repl:
                out[i] = repl
                placed = True
                break
        if placed:
            continue
        # Otherwise a borrowed chord on a weak bar (2nd/4th of the phrase).
        weak = [i for i in idxs if (i - p0) % 2 == 1 and i != last]
        rng.shuffle(weak)
        if weak:
            choice = rng.choice([b for b in borrowed if b != out[weak[0]]] or borrowed)
            out[weak[0]] = choice
    return out


def resolve_progression(progression: list, scale: str, complexity: float, secondary_dominants: bool = False, tritone_sub: bool = False) -> list:
    """Pre-apply substitutions once so chords and melody share identical harmony.

    Call this in the route before generating chords/melody, then pass the result as
    ``resolved_progression`` to ``generate_chords`` and as ``progression`` to
    ``generate_melody``.  Both generators will then target the same chord tones.
    """
    return [_apply_substitution(roman, scale, complexity, secondary_dominants, tritone_sub) for roman in progression]


def _is_dominant(roman: str) -> bool:
    """Return True if roman is a dominant V or a raised secondary dominant (II, III, VI)."""
    s = roman.lstrip("b#")
    for suffix in ("m7b5", "mM7", "dim7", "maj7", "9sus4", "7sus4", "sus2", "sus4", "add11", "add9", "aug", "dim", "m6", "m9", "6", "9"):
        if s.lower().endswith(suffix):
            s = s[: -len(suffix)]
            break
    return s in ("V", "II", "III", "VI")


def generate_chords(
    style: dict,
    key: str,
    scale: str,
    bars: int,
    complexity: float,
    variation: float,
    progression: list | None = None,
    resolved_progression: list | None = None,
    melody_ceiling: int | None = None,
    kick_times: list[float] | None = None,
    melody_rests: list | None = None,
    harmony_complexity: float | None = None,
    prev_voicing: list[int] | None = None,
    push_windows: set[int] | None = None,
    section_type: str | None = None,
) -> List[NoteEvent]:
    """`harmony_complexity` — the value that decides chords-per-bar, shared with
    melody/bass so all three parts agree on the harmonic grid (falls back to
    `complexity`). `prev_voicing` — the final voicing of the previous section,
    so voice leading continues smoothly across section boundaries instead of
    resetting to root position at every seam.
    """
    events: List[NoteEvent] = []

    def _in_melody_rest(beat: float) -> bool:
        """True when `beat` falls inside a melody rest — chords answer in the gap."""
        return bool(melody_rests) and any(rs <= beat < re for rs, re in melody_rests)
    if progression is None:
        templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
        progression = random.choice(templates)

    # Use pre-resolved progression when provided so chords and melody stay in sync.
    # Otherwise apply substitutions per-chord internally (legacy / standalone behaviour).
    prog_source = resolved_progression if resolved_progression is not None else None
    prog_len = len(resolved_progression if resolved_progression is not None else progression)

    ext = style.get("chord_extensions", {})
    allow_7th_prob = ext.get("allow_7th", 0.3)
    allow_9th_prob = ext.get("allow_9th", 0.1)
    # Power chords: root+5th(+octave), no 3rd — the only voicing that stays
    # clear under distortion. Replaces extensions, alterations and voice-led
    # inversions (a 5th-in-the-bass power chord reads as a different chord).
    power_chords = bool(style.get("power_chords", False))
    swing_amount = style.get("drums", {}).get("swing", 0.0)

    altered_dominant_prob = style.get("altered_dominant_prob", 0.0)
    # Instrument playing profile for the chords part (None for custom styles
    # without instrumentation — every use below falls back to legacy behavior).
    _ch_profile = instrumentation_for(style).get("chords")

    # Strum timing: seconds per string. Slow styles (lofi/soul) ~20ms, tight styles (funk/jazz) ~5-8ms.
    # Stored as beats; converts to real time at runtime based on BPM (handled by sequencer/DAW).
    # The style knob wins; otherwise the instrument decides (a guitar strums at
    # ~18ms, a pad plays true block chords at 0).
    _default_strum = _ch_profile["strum"] if _ch_profile else 0.010
    strum_speed = style.get("strum_speed", _default_strum)

    # Staccato factor: shorten note durations for styles that want sharp articulation.
    # Only applies when duration is computed from chord_rhythm steps (not comp_duration_override).
    staccato_factor = style.get("staccato_factor", 1.0)

    # Register: lower by default to leave headroom for melody above.
    # Styles that use high-register pads can override via "chord_register".
    ch_low, ch_high = style.get("chord_register", [48, 72])
    if _ch_profile:
        # Style register is taste; instrument range is physics — honor both.
        ch_low, ch_high = clamp_range([ch_low, ch_high], _ch_profile["range"])

    # Keep chord voicings below the melody's range so they don't fight for the same register
    if melody_ceiling is not None:
        ch_high = min(ch_high, melody_ceiling - 1)
        ch_low  = min(ch_low, ch_high - 12)  # ensure at least an octave of range

    # comp_style overrides chord_rhythm with a curated comping pattern
    comp_style = style.get("comp_style")
    # Per-section comp variants: the style can re-voice its comp per section
    # ("verse" sparser, "intro"/"outro" ringing holds) so the rhythm part
    # arranges across the song instead of chugging one pattern wall-to-wall
    # (measured: rock_drive played identical 8ths through all 81 bars).
    _comp_variants = style.get("comp_section_variants") or {}
    if section_type and section_type in _comp_variants:
        comp_style = _comp_variants[section_type]
    # fmt: off
    _COMP_RHYTHMS = {
        # Jazz: sparse syncopated — "and of 1", beat 2, "and of 3", beat 4
        "jazz_comp":   [0,0,0,1,0,1,0,0,0,0,0,1,0,1,0,0],
        # Bossa nova: 1, "and of 2", "and of 3", beat 4 — classic Brazilian comp
        "bossa_comp":  [1,0,0,0,0,1,0,0,0,0,1,0,0,0,1,0],
        # Funk: tight stabs with anticipations
        "funk_stab":   [1,0,1,0,0,1,0,1,0,1,0,0,1,0,0,1],
        # Lofi: lazy strum on 1 and late upbeat
        "lofi_strum":  [1,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0],
        # Pad: hold — single hit per bar
        "pad_hold":    [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        # House: offbeat 8th-note stabs
        "house_stab":  [0,0,1,0,0,0,1,0,0,0,1,0,0,0,1,0],
        # Synthwave: quarter-note gated stabs
        "synth_gate":  [1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0],
        # Rock: driving straight 8th-note chugs
        "rock_drive":  [1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0],
        # Rock verse: damped hits with space — 1, and-of-2, and-of-3, 4
        "rock_verse":  [1,0,0,0,0,0,1,0,0,0,1,0,1,0,0,0],
        # Metal: palm-muted gallop — 8th + two 16ths on every beat
        "palm_mute":   [1,0,1,1,1,0,1,1,1,0,1,1,1,0,1,1],
        # Doom: crushing hit on 1 and the and-of-3, ringing until the next hit
        "doom_crush":  [1,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0],
    }
    # fmt: on

    # Riff mode: the guitar plays a low-register pedal-tone figure (the song's
    # riff), not a comped voicing. Rendered here as power-chord stabs on the
    # figure's accents and single-note palm-muted chugs elsewhere. The riff is a
    # song-level object (app.generators.riff) that the bass renders in unison.
    if comp_style == "riff":
        return _render_riff_guitar(
            style, key, scale, bars, prog_source or progression, section_type,
            ch_low, ch_high, style.get("velocity_base", 74),
            style.get("vel_arc_start", 0.75), swing_amount, strum_speed)

    chord_rhythm = _COMP_RHYTHMS.get(comp_style) if comp_style else style.get("chord_rhythm")

    # Comp style also affects note duration
    _COMP_DURATIONS = {
        "jazz_comp":   0.38,   # punchy jazz comping
        "bossa_comp":  0.48,   # slightly rounder bossa feel
        "funk_stab":   0.38,   # tight staccato
        "lofi_strum":  None,   # auto (fill to next hit)
        "pad_hold":    3.80,   # long sustain
        "house_stab":  0.42,   # offbeat 8th-note stabs
        "synth_gate":  0.20,   # very short = gated synth
        "rock_drive":  0.40,   # driven but not staccato
        "rock_verse":  0.35,   # damped verse hits
        "palm_mute":   0.11,   # tight chug — the mute IS the sound
        "doom_crush":  None,   # auto (ring until the next hit)
    }
    comp_duration_override = _COMP_DURATIONS.get(comp_style) if comp_style else None

    # Open voicing: jazz/soul/lofi occasionally drop an inner voice for a sparser sound
    open_voicing_prob = style.get("open_voicing_prob", 0.0)
    drop_2_prob = style.get("drop_2_prob", 0.0)
    passing_chord_prob = style.get("passing_chord_prob", 0.0)
    turnaround_prob = style.get("turnaround_prob", 0.0)

    vel_arc_start = style.get("vel_arc_start", 0.75)
    velocity_base = style.get("velocity_base", 74)

    def _styled_arc(bar: int, total: int, base: int, start: float) -> int:
        t = bar / max(1, total - 1)
        return max(1, min(127, int(base * (start + (1.0 - start) * t))))

    beats_per_bar = 4
    phrase_beats = beats_per_bar * 4  # 4-bar phrase = 16 beats
    _harmony_cplx = complexity if harmony_complexity is None else harmony_complexity
    chords_per_bar = 2 if _harmony_cplx > 0.6 else 1
    beats_per_chord = beats_per_bar / chords_per_bar
    total_chords = bars * chords_per_bar
    step = 0.25  # 16th note
    ticks_per_beat = 480

    def _swing(beat: float) -> float:
        if swing_amount < 0.01:
            return beat
        tick = int(beat * ticks_per_beat)
        return apply_swing(tick, swing_amount, ticks_per_beat) / ticks_per_beat

    prev_pitches: list[int] = sorted(prev_voicing) if prev_voicing else []  # tracks the sounded voicing for voice leading

    for i in range(total_chords):
        if prog_source is not None:
            roman = prog_source[i % prog_len]
        else:
            roman = _apply_substitution(progression[i % prog_len], scale, complexity)
        allow_7th = should_trigger(allow_7th_prob)
        allow_9th = should_trigger(allow_9th_prob) if allow_7th else False
        pitches = roman_to_chord(roman, key, scale, octave=4, allow_7th=allow_7th, allow_9th=allow_9th)
        # Core tones (triad + any 7th) — what the de-cluster must never drop; the
        # 9th/altered extensions on top of these are the droppable tensions.
        core_pcs = {p % 12 for p in roman_to_chord(roman, key, scale, octave=4, allow_7th=allow_7th)}

        if power_chords:
            # Root anchored lowest in the register; extensions discarded.
            root = pitches[0]
            while root < ch_low:
                root += 12
            while root > ch_high - 7 and root - 12 >= ch_low:
                root -= 12
            pitches = [root, root + 7]
            if root + 12 <= ch_high:
                pitches.append(root + 12)
            core_pcs = {p % 12 for p in pitches}

        # Altered dominant: on V / secondary dominant chords, substitute a b9, #9, or b13
        if altered_dominant_prob > 0 and not power_chords and _is_dominant(roman) and allow_7th and should_trigger(altered_dominant_prob):
            chord_root = pitches[0]
            alt_interval = random.choice([13, 15, 20])  # b9, #9, b13
            # Remove natural 9th if present, then add the alteration
            pitches = [p for p in pitches if p != chord_root + 14]
            pitches.append(chord_root + alt_interval)

        if prev_pitches and not power_chords:
            pitches = _voice_lead(pitches, prev_pitches)
        else:
            pitches = sorted(pitches)

        pitches = _clamp_register(pitches, low=ch_low, high=ch_high)

        # Open voicing: drop an inner voice occasionally for an airy jazz/acoustic feel
        sounded = sorted(pitches)
        if open_voicing_prob > 0 and len(sounded) >= 4 and should_trigger(open_voicing_prob):
            # Remove one middle voice (index 1 or 2), keep root and top
            drop_idx = random.randint(1, len(sounded) - 2)
            sounded = sounded[:drop_idx] + sounded[drop_idx + 1:]
        pitches = sounded

        # Drop-2 voicing: drop second-highest note an octave (jazz open voicing)
        if drop_2_prob > 0 and len(pitches) >= 4 and should_trigger(drop_2_prob):
            pitches = _drop_2(pitches)
            pitches = _clamp_register(pitches, low=ch_low, high=ch_high)

        pitches = _cap_polyphony(pitches, _ch_profile["polyphony"] if _ch_profile else None)
        # Open any internal semitone cluster so the chord reads clearly (not mud).
        pitches = _declutter(pitches, core_pcs, ch_low, ch_high)
        prev_pitches = sorted(pitches)  # record the clamped (sounded) voicing

        start_beat = i * beats_per_chord
        bar_num = int(start_beat / beats_per_bar)
        is_downbeat = (start_beat % beats_per_bar) < 0.01
        base_vel = _styled_arc(bar_num, bars, velocity_base, vel_arc_start)
        base_vel = int(base_vel * phrase_breath_factor(bar_num))
        vel = (base_vel + 6 if is_downbeat else base_vel) + random.randint(-5, 5)

        # Chromatic passing chord: brief half-step approach to this chord root, fired 0.25 beats before downbeat
        if i > 0 and passing_chord_prob > 0 and (start_beat % beats_per_bar) < 0.01 and should_trigger(passing_chord_prob):
            approach_start = start_beat - 0.25
            if approach_start >= 0:
                chord_root_midi = roman_to_chord(roman, key, scale, octave=4)[0]
                approach_root = chord_root_midi - 1   # half-step below
                for p in [approach_root, approach_root + 7]:   # root + fifth dyad
                    # Clamp passing chord notes to the same register ceiling as regular chords
                    clamped_p = p
                    while clamped_p > ch_high and clamped_p - 12 >= 0:
                        clamped_p -= 12
                    events.append(NoteEvent(
                        pitch=min(127, max(0, clamped_p)),
                        start=max(0.0, _swing(approach_start) + timing_jitter(0.010)),
                        duration=0.18,
                        velocity=max(1, min(127, vel - 28)),
                        channel=0,
                    ))

        # Turnaround: detect last-chord slot of a 4-bar phrase and replace with ii-V
        phrase_pos = start_beat % phrase_beats if phrase_beats > 0 else 0
        is_last_phrase_chord = (
            turnaround_prob > 0
            and phrase_beats > 0
            and (phrase_pos + beats_per_chord >= phrase_beats)
            and start_beat > 0
            and should_trigger(turnaround_prob)
        )

        if is_last_phrase_chord:
            ta_scale_is_minor = scale in ("minor", "phrygian", "locrian", "pentatonic_minor")
            ta_chords = ["iim7b5", "V"] if ta_scale_is_minor else ["ii", "V"]
            ta_dur = beats_per_chord / 2.0
            for ta_i, ta_roman in enumerate(ta_chords):
                ta_start = start_beat + ta_i * ta_dur
                ta_pitches = roman_to_chord(ta_roman, key, scale, octave=4, allow_7th=True)
                if prev_pitches:
                    ta_pitches = _voice_lead(ta_pitches, prev_pitches)
                else:
                    ta_pitches = sorted(ta_pitches)
                ta_pitches = _clamp_register(ta_pitches, low=ch_low, high=ch_high)
                ta_pitches = _cap_polyphony(ta_pitches, _ch_profile["polyphony"] if _ch_profile else None)
                prev_pitches = sorted(ta_pitches)
                ta_vel = vel - random.randint(2, 8)
                ta_sorted = sorted(ta_pitches)
                n_ta = len(ta_sorted)
                for note_idx, pitch in enumerate(ta_sorted):
                    events.append(NoteEvent(
                        pitch=min(127, max(0, pitch)),
                        start=max(0.0, _swing(ta_start) + timing_jitter(0.012) + note_idx * strum_speed),
                        duration=min(ta_dur * 0.75, 1.5),
                        velocity=max(1, min(127, ta_vel + _voice_vel_offset(note_idx, n_ta))),
                        channel=0,
                    ))
        else:
            if chord_rhythm:
                num_steps = int(beats_per_chord / step)
                bar_offset = start_beat % beats_per_bar
                base_idx = int(bar_offset / step)

                # Pre-compute which steps have hits so we can calculate sustain to next hit
                hit_steps = [
                    s for s in range(num_steps)
                    if chord_rhythm[(base_idx + s) % len(chord_rhythm)]
                ]

                # Guarantee a hit at the start of EVERY chord window, not just the
                # bar's first: at 2 chords per bar, a comp rhythm whose hits all
                # sit in the first half of the bar (pad_hold's [1,0,...]) left the
                # second window's slice empty — every other chord of the
                # progression was silently dropped while the first one rang
                # through it (bass/melody kept playing the missing chord's notes
                # against it).
                if 0 not in hit_steps:
                    hit_steps = [0] + hit_steps

                sorted_pitches = sorted(pitches)
                n = len(sorted_pitches)

                for hi, s in enumerate(hit_steps):
                    # Hold until the next hit (or end of the chord window), then leave a small gap
                    steps_to_next = (hit_steps[hi + 1] - s) if hi + 1 < len(hit_steps) else (num_steps - s)
                    if comp_duration_override is not None:
                        # Never ring past this chord's window: pad_hold's 3.8-beat
                        # hold was tuned for one chord per bar and smeared across
                        # the NEXT chord at 2 chords per bar.
                        duration = min(comp_duration_override, (num_steps - s) * step * 0.95)
                    else:
                        duration = max(step * 0.8, steps_to_next * step * 0.92)
                        if staccato_factor < 1.0:
                            duration = max(step * 0.5, duration * staccato_factor)

                    beat_of_hit = start_beat + s * step

                    # Anticipation ("push"): the NEW chord lands an 8th early,
                    # on the "and of 4" before its window — the played feel a
                    # strict grid never has. WHICH changes push comes from the
                    # shared push_windows map (the bass observes the same map,
                    # so the band pushes together); pad-style holds never push
                    # (a sustained wash arriving early just smears). Standalone
                    # calls without a map fall back to an independent roll.
                    _pushes = (i in push_windows) if push_windows is not None else                         (i > 0 and should_trigger(style.get("chord_anticipation_prob", 0.15)))
                    if hi == 0 and s == 0 and i > 0 and comp_style != "pad_hold" and _pushes:
                        beat_of_hit -= 0.5
                        duration += 0.5
                    kick_boost = 8 if kick_times and any(abs(k - beat_of_hit) < 0.12 for k in kick_times) else 0
                    # Call-and-response: chords step forward (louder, less duck) when
                    # the melody is resting, receding again once it re-enters.
                    rest_boost = 7 if _in_melody_rest(beat_of_hit) else 0
                    hit_start = _swing(beat_of_hit) + timing_jitter(style_jitter(style))
                    hit_vel = vel + kick_boost + rest_boost - random.randint(0, 10 - min(6, rest_boost))
                    # Driving guitar comps accent the quarter notes — flat 8ths
                    # sound like a machine, accented ones like a wrist.
                    if comp_style in ("rock_drive", "palm_mute") and (s * step) % 1.0 > 0.01:
                        hit_vel -= 7
                    sorted_pitches_hit = sorted(pitches)
                    n_hit = len(sorted_pitches_hit)
                    for note_idx, pitch in enumerate(sorted_pitches_hit):
                        strum_vel_offset = _voice_vel_offset(note_idx, n_hit)
                        strum_time = note_idx * strum_speed
                        events.append(NoteEvent(
                            pitch=min(127, max(0, pitch)),
                            start=max(0.0, hit_start + strum_time),
                            duration=duration,
                            velocity=max(1, min(127, hit_vel + strum_vel_offset)),
                            channel=0,
                        ))
            else:
                duration = comp_duration_override if comp_duration_override is not None else beats_per_chord * 0.95
                if comp_duration_override is None and staccato_factor < 1.0:
                    duration = max(step * 0.5, duration * staccato_factor)
                jitter = timing_jitter(style_jitter(style))
                sorted_pitches = sorted(pitches)
                n = len(sorted_pitches)
                for note_idx, pitch in enumerate(sorted_pitches):
                    strum_vel_off = _voice_vel_offset(note_idx, n)
                    strum_time = note_idx * 0.010
                    events.append(NoteEvent(
                        pitch=min(127, max(0, pitch)),
                        start=max(0.0, _swing(start_beat) + jitter + strum_time),
                        duration=duration,
                        velocity=max(1, min(127, vel + strum_vel_off)),
                        channel=0,
                    ))

    return events
