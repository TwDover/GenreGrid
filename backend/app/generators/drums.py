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
from app.core.constants import DRUM_MAP, DRUM_CHANNEL
from app.services.variation import should_trigger
from app.services.humanize import micro_jitter
from app.theory.rhythm import apply_swing


# ── Velocity accent weights for every 16th-note position in one bar ──────────
# Index 0 = beat 1, 4 = beat 2, 8 = beat 3, 12 = beat 4.
# Research-based: downbeats > off-beats; "and" (index 2,6,10,14) slightly
# accented to push the groove forward; "e" and "ah" are passing tones.
_HAT_VEL_WEIGHTS = [
    1.00, 0.52, 0.83, 0.50,   # beat 1  (1, e, and, ah)
    0.88, 0.50, 0.75, 0.48,   # beat 2
    0.93, 0.52, 0.83, 0.50,   # beat 3
    0.88, 0.52, 0.79, 0.48,   # beat 4  (and-of-4 nudged up: upbeat anticipation)
]

# 4-bar phrase dynamics applied to ALL instruments: quiet intro → peak → breathe.
_PHRASE_DYN = [0.89, 0.96, 1.00, 0.93]

# Kick downbeat (beat 1) velocity base — loudest hit in the bar.
_KICK_VEL_BASE = 112

# Standard snare velocity base
_SNARE_VEL_BASE = 106


def _humanize(style: dict) -> float:
    """User humanize setting in [0, 1]. Injected into style by the route handler."""
    return float(style.get("_humanize_scale", 0.5))


def _jitter(inst: str, h: float) -> float:
    """Per-instrument timing jitter in beats.

    Kick is the tightest reference point; hats are the loosest.
    h = humanize setting 0-1.
    """
    # (min_spread_beats, max_spread_beats)
    ranges = {
        "kick":  (0.003, 0.010),
        "snare": (0.002, 0.008),
        "hat":   (0.005, 0.016),
        "ghost": (0.007, 0.022),
        "perc":  (0.006, 0.016),
        "fill":  (0.004, 0.012),
    }
    lo, hi = ranges.get(inst, (0.004, 0.014))
    spread = lo + h * (hi - lo)
    return random.uniform(-spread, spread)


def _plan_open_hats(bar_in_pair: int, complexity: float) -> set:
    """Return the set of beat-in-bar positions that should use open hat.

    Positions are planned once per bar so they land musically (not randomly
    scattered across every hat hit). Classic placements:
      - and-of-4 (position 3.5): closes on next beat 1 → very common
      - and-of-2 (position 1.5): at higher complexity in bar 2
    """
    positions = set()
    if bar_in_pair == 1:
        if should_trigger(0.42 + complexity * 0.12):
            positions.add(3.5)
        if complexity > 0.55 and should_trigger(0.22):
            positions.add(1.5)
    else:
        # Bar 1: open hat only at higher complexity
        if complexity > 0.65 and should_trigger(0.18):
            positions.add(3.5)
    return positions


# Voices a mined fill layers over the base groove (kick/closed_hat/ride stay as
# the groove's pulse; the fill adds toms, snares, crash, claps, open hats).
_FILL_LAYER_KEYS = frozenset({"tom_hi", "tom_mid", "tom_lo", "snare", "clap", "crash", "open_hat"})

# Relative energy of each section type — drives how hard the fill into that
# section hits (big fill into a chorus, barely-there fill into an outro).
_SECTION_ENERGY = {
    "intro": 0.30, "verse": 0.55, "pre_chorus": 0.70, "chorus": 1.00,
    "post_chorus": 0.80, "bridge": 0.60, "instrumental_solo": 0.75, "outro": 0.25,
}


def generate_drums(
    style: dict,
    bars: int,
    complexity: float,
    variation: float,
    section_end_bars: list[int] | None = None,
    is_loop: bool = False,
    section_type: str | None = None,
    next_section_type: str | None = None,
) -> List[NoteEvent]:
    """`section_type` / `next_section_type` — song-section context (loop-mode song
    building). The groove *arranges* per section instead of playing the same beat
    at every point in the song: intros strip to kick+hats, pre-choruses build hat
    density toward the drop, choruses open with a crash and play the fullest
    groove, bridges flip to a half-time feel, outros decay bar over bar. The fill
    at a section boundary is sized by the energy of what comes next, and any
    section leading into a chorus gets a snare-roll build. Both default to None
    (plain loop / non-song generation), which preserves the original behavior.
    """
    events: List[NoteEvent] = []
    drum_cfg = style.get("drums", {})
    h = _humanize(style)

    sec = section_type or ""
    is_intro     = sec == "intro"
    is_chorus    = sec in ("chorus", "post_chorus")
    is_prechorus = sec == "pre_chorus"
    is_outro     = sec == "outro"
    # Bridge half-time: snare moves to beat 3, hats thin to 8ths, kick strips back.
    half_time = sec == "bridge" and drum_cfg.get("half_time_bridge", True)
    next_energy = _SECTION_ENERGY.get(next_section_type) if next_section_type else None

    hat_density        = drum_cfg.get("hat_density", 0.7)
    triplet_prob       = drum_cfg.get("triplet_probability", 0.2)
    snare_beats        = drum_cfg.get("snare_standard_beats", [2, 4])
    if half_time:
        snare_beats = [3]
    swing_amount       = drum_cfg.get("swing", 0.0)
    use_ride           = drum_cfg.get("use_ride", False)
    use_clap           = drum_cfg.get("use_clap", False)
    crash_on_bar_1     = drum_cfg.get("crash_on_bar_1", False)
    tom_fills          = drum_cfg.get("tom_fills", False)
    hat_roll_prob      = drum_cfg.get("hat_roll_prob", 0.0)
    open_hat_style     = drum_cfg.get("open_hat_style", "random")
    snare_upbeat_prob  = drum_cfg.get("snare_upbeat_prob", 0.0)
    snare_beat3_prob   = drum_cfg.get("snare_beat3_prob", 0.0)
    ghost_note_prob    = drum_cfg.get(
        "ghost_note_prob",
        swing_amount * 0.8 if swing_amount >= 0.3 else 0.0,
    )
    ride_style  = drum_cfg.get("ride_style", "default")
    edm_drops   = drum_cfg.get("edm_drops", False)
    perc_layers = drum_cfg.get("perc_layers", [])
    flam_prob   = drum_cfg.get("flam_prob", 0.0)
    mined_fills = drum_cfg.get("fills")     # mined section-transition fills (groove prior)
    mined_hat_pattern = drum_cfg.get("hat_pattern")   # per-step closed-hat placement prob
    mined_hat_vel     = drum_cfg.get("hat_vel")       # per-step closed-hat velocity accent

    section_ends = set(section_end_bars) if section_end_bars else set()
    hat_note     = DRUM_MAP["ride"] if use_ride else DRUM_MAP["closed_hat"]

    beats_per_bar  = 4
    step           = 0.25      # sixteenth note
    ticks_per_beat = 480
    hat_base_vel   = 74        # peak velocity for the 16-step accent curve

    # Decide hat subdivision mode once per 4-bar phrase.
    phrase_hat_modes: dict[int, bool] = {}
    for bar in range(bars):
        phrase_idx = bar // 4
        if phrase_idx not in phrase_hat_modes:
            phrase_hat_modes[phrase_idx] = should_trigger(triplet_prob)

    # Primary / secondary ghost note positions (beat-in-bar, 0-indexed)
    PRIMARY_GHOSTS   = {1.75, 3.75}
    SECONDARY_GHOSTS = {0.25, 0.75, 1.25, 2.25, 2.75, 3.25}

    for bar in range(bars):
        bar_start   = bar * beats_per_bar
        bar_in_pair = bar % 2
        bar_in_8    = bar % 8

        # 4-bar phrase energy envelope — applied to all instruments
        phrase_dyn = _PHRASE_DYN[bar % 4]

        # Outro: the whole kit decays bar over bar so the song winds down
        if is_outro:
            phrase_dyn *= 1.0 - 0.38 * (bar / max(1, bars - 1))

        # Per-section hat scaling: stripped intro, building pre-chorus, thinning
        # outro, boosted chorus. Verse/bridge/solo stay at the style's density.
        if is_intro:
            sec_hat = 0.60
        elif is_prechorus:
            sec_hat = min(1.0, 0.78 + 0.50 * (bar / max(1, bars - 1)))
        elif is_outro:
            sec_hat = max(0.35, 1.0 - 0.50 * (bar / max(1, bars - 1)))
        elif is_chorus:
            sec_hat = 1.12
        else:
            sec_hat = 1.0

        # Hat breath: bar 4 of every 8-bar phrase slightly thinner
        hat_breath = 0.72 if bar_in_8 == 4 else 1.0

        # ── Crash ──────────────────────────────────────────────────────────────
        # A chorus always announces itself with a crash on its first downbeat,
        # independent of the style's crash_on_bar_1 flag.
        if (is_chorus and bar == 0) or (
                crash_on_bar_1 and (bar == 0 or (complexity > 0.7 and bar % 4 == 0))):
            events.append(NoteEvent(
                pitch=DRUM_MAP["crash"],
                start=bar_start + _jitter("fill", h),
                duration=0.5,
                velocity=min(127, int((100 + random.randint(-6, 6)) * phrase_dyn)),
                channel=DRUM_CHANNEL,
            ))

        # ── Kick ───────────────────────────────────────────────────────────────
        kick_pattern = drum_cfg.get("kick_pattern")
        if kick_pattern:
            kick_beats_bar1 = [
                i * step for i, on in enumerate(kick_pattern)
                if on and should_trigger(0.88 + variation * 0.10)
            ]
            # Guarantee beat 1
            if not any(b < step for b in kick_beats_bar1):
                kick_beats_bar1.insert(0, 0.0)
        else:
            kick_beats_bar1 = [0.0]
            if complexity > 0.35:
                kick_beats_bar1.append(2.0)
            if complexity > 0.65 and should_trigger(0.5):
                kick_beats_bar1.append(2.5)
            if should_trigger(variation * 0.3):
                kick_beats_bar1.append(0.75)

        # Bar 2: apply variation strategy
        kick_beats = (
            _vary_kick_beats_bar2(kick_beats_bar1, complexity)
            if bar_in_pair == 1
            else list(kick_beats_bar1)
        )

        # Intro: strip the kick to its anchors — the groove arrives with the verse
        if is_intro:
            kick_beats = [b for b in kick_beats if b in (0.0, 2.0)] or [0.0]
        # Half-time bridge: kick on 1, optional lazy "and of 3"
        elif half_time:
            kick_beats = [0.0] + ([2.5] if complexity > 0.5 and should_trigger(0.4) else [])

        for b in kick_beats:
            t      = bar_start + b
            t_tick = int(t * ticks_per_beat)
            t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
            beat_in_bar = round(b % beats_per_bar, 4)
            if beat_in_bar < 0.01:
                kick_vel = _KICK_VEL_BASE
            elif abs(beat_in_bar - 2.0) < 0.01:
                kick_vel = int(_KICK_VEL_BASE * 0.88)
            else:
                kick_vel = int(_KICK_VEL_BASE * 0.80)
            # Phrase envelope + per-bar randomness
            kick_vel = int(kick_vel * phrase_dyn) + random.randint(-6, 6)
            events.append(NoteEvent(
                pitch=DRUM_MAP["kick"],
                start=t_tick / ticks_per_beat + _jitter("kick", h),
                duration=0.1,
                velocity=max(1, min(127, kick_vel)),
                channel=DRUM_CHANNEL,
            ))

        # ── Snare ──────────────────────────────────────────────────────────────
        # Intro carries no backbeat — kick and hats set the pulse, the snare
        # lands when the first real section starts.
        for snare_b in ([] if is_intro else snare_beats):
            b_f    = float(snare_b) - 1.0
            t      = bar_start + b_f
            t_tick = int(t * ticks_per_beat)
            t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
            snare_vel = int(_SNARE_VEL_BASE * phrase_dyn) + random.randint(-8, 8)

            # Flam: tiny grace note just before the main hit (adds crack/texture)
            if flam_prob > 0 and should_trigger(flam_prob):
                flam_start = max(0.0, t_tick / ticks_per_beat - 0.022)
                events.append(NoteEvent(
                    pitch=DRUM_MAP["snare"],
                    start=flam_start,
                    duration=0.04,
                    velocity=max(1, min(127, 38 + random.randint(-6, 6))),
                    channel=DRUM_CHANNEL,
                ))

            events.append(NoteEvent(
                pitch=DRUM_MAP["snare"],
                start=t_tick / ticks_per_beat + _jitter("snare", h),
                duration=0.1,
                velocity=max(1, min(127, snare_vel)),
                channel=DRUM_CHANNEL,
            ))

        # Snare upbeat hits ("and of 1", "and of 3")
        if snare_upbeat_prob > 0 and not is_intro and not half_time:
            for upbeat_b in [0.5, 2.5]:
                if should_trigger(snare_upbeat_prob):
                    t = bar_start + upbeat_b
                    t_tick = int(t * ticks_per_beat)
                    t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                    upbeat_vel = int((70 + random.randint(-8, 8)) * phrase_dyn)
                    events.append(NoteEvent(
                        pitch=DRUM_MAP["snare"],
                        start=t_tick / ticks_per_beat + _jitter("snare", h),
                        duration=0.1,
                        velocity=max(1, min(127, upbeat_vel)),
                        channel=DRUM_CHANNEL,
                    ))

        # Beat-3 snare (funk / soul syncopation)
        if snare_beat3_prob > 0 and not is_intro and not half_time and should_trigger(snare_beat3_prob):
            t = bar_start + 2.0
            t_tick = int(t * ticks_per_beat)
            t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
            b3_vel = int((78 + random.randint(-10, 10)) * phrase_dyn)
            events.append(NoteEvent(
                pitch=DRUM_MAP["snare"],
                start=t_tick / ticks_per_beat + _jitter("snare", h),
                duration=0.1,
                velocity=max(1, min(127, b3_vel)),
                channel=DRUM_CHANNEL,
            ))

        # Clap layered on snare beats
        if use_clap and not is_intro:
            for snare_b in snare_beats:
                b_f    = float(snare_b) - 1.0
                t      = bar_start + b_f
                t_tick = int(t * ticks_per_beat)
                t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                clap_vel = int((88 + random.randint(-8, 8)) * phrase_dyn)
                events.append(NoteEvent(
                    pitch=DRUM_MAP["clap"],
                    start=t_tick / ticks_per_beat + _jitter("snare", h),
                    duration=0.05,
                    velocity=max(1, min(127, clap_vel)),
                    channel=DRUM_CHANNEL,
                ))

        # ── Hi-hats / ride ────────────────────────────────────────────────────
        use_triplet = phrase_hat_modes[bar // 4]
        if use_triplet:
            # 12 triplet 8th notes per bar (3 per beat × 4 beats)
            hat_steps = [bar_start + i / 3.0 for i in range(12)]
        else:
            hat_steps = [bar_start + i * step for i in range(int(beats_per_bar / step))]
        # Half-time bridge: hats fall back to the 8th-note grid
        if half_time and not use_triplet:
            hat_steps = [t for t in hat_steps if round((t - bar_start) % 0.5, 4) < 0.01]

        # EDM drop: strip hats from beat 2 onward on section-end bars
        is_section_end  = bar in section_ends
        edm_build_active = edm_drops and is_section_end and complexity > 0.4

        # Pre-plan open hat positions for this bar (musical placement)
        if open_hat_style == "offbeats":
            # House/funk: intentional open hat on all 8th off-beats
            open_hat_positions: set = set()  # handled inline below
            use_planned_open = False
        else:
            open_hat_positions = set() if is_intro else _plan_open_hats(bar_in_pair, complexity)
            use_planned_open = True

        rolled_positions: set[float] = set()

        if use_ride and ride_style == "jazz":
            # Classic "spang-a-lang": quarter notes + swing 8ths on ride
            _JAZZ_RIDE = [1, 0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 1, 0, 0, 0]
            for s, on in enumerate(_JAZZ_RIDE):
                if not on:
                    continue
                t = bar_start + s * step
                beat_frac = round(s * step % 1.0, 4)
                base_v = 66 if beat_frac < 0.01 else (54 if abs(beat_frac - 0.5) < 0.01 else 46)
                vel = int(base_v * phrase_dyn) + random.randint(-5, 5)
                t_tick = int(t * ticks_per_beat)
                t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                events.append(NoteEvent(
                    pitch=DRUM_MAP["ride"],
                    start=t_tick / ticks_per_beat + _jitter("hat", h),
                    duration=0.1,
                    velocity=max(1, min(127, vel)),
                    channel=DRUM_CHANNEL,
                ))
            # Hi-hat "chick" on beats 2 and 4
            for chick_b in [1.0, 3.0]:
                t = bar_start + chick_b
                t_tick = int(t * ticks_per_beat)
                t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                events.append(NoteEvent(
                    pitch=DRUM_MAP["closed_hat"],
                    start=t_tick / ticks_per_beat + _jitter("hat", h),
                    duration=0.04,
                    velocity=max(1, min(127, int((56 + random.randint(-8, 8)) * phrase_dyn))),
                    channel=DRUM_CHANNEL,
                ))
        else:
            for t in hat_steps:
                if edm_build_active and (t - bar_start) >= 1.5:
                    continue

                pos_key  = round(t - bar_start, 4)
                step_idx = round(pos_key / step)

                # Placement: a real drummer's per-step hat probability (mined) on the
                # straight grid, else the procedural density.
                if mined_hat_pattern is not None and not use_triplet:
                    place_p = mined_hat_pattern[step_idx % 16] * hat_breath
                else:
                    place_p = hat_density * hat_breath * (0.70 + complexity * 0.30)
                place_p = min(1.0, place_p * sec_hat)
                if not should_trigger(place_p):
                    continue

                beat_frac = round((t - bar_start) % 1.0, 4)

                if pos_key in rolled_positions:
                    continue

                is_eighth = beat_frac < 0.01 or abs(beat_frac - 0.5) < 0.01

                # 16-step accent weight — mined velocity curve when available.
                if not use_triplet:
                    accent = (mined_hat_vel[step_idx % 16] if mined_hat_vel is not None
                              else _HAT_VEL_WEIGHTS[step_idx % 16])
                else:
                    # Triplets: accent 1st of each triplet group, weaker on 2nd/3rd
                    triplet_pos = round(pos_key * 3)
                    accent = 0.88 if triplet_pos % 3 == 0 else (0.62 if triplet_pos % 3 == 1 else 0.50)

                vel = int(hat_base_vel * accent * phrase_dyn * hat_breath) + random.randint(-5, 5)

                # Trap hi-hat roll: replace 8th-note hit with 3× 32nd notes
                if hat_roll_prob > 0 and is_eighth and not use_ride and should_trigger(hat_roll_prob):
                    for r_i, r_offset in enumerate([0.0, 0.125, 0.25]):
                        r_t    = t + r_offset
                        r_tick = int(r_t * ticks_per_beat)
                        r_tick = apply_swing(r_tick, swing_amount, ticks_per_beat)
                        # First hit loudest, middle softer, last fades
                        r_vel  = vel if r_i == 0 else (vel - 14 if r_i == 1 else vel - 8)
                        events.append(NoteEvent(
                            pitch=DRUM_MAP["closed_hat"],
                            start=r_tick / ticks_per_beat + _jitter("hat", h),
                            duration=0.05,
                            velocity=max(1, min(127, r_vel)),
                            channel=DRUM_CHANNEL,
                        ))
                    rolled_positions.add(round(pos_key + 0.25, 4))
                    continue

                # Determine open vs closed
                if use_ride:
                    note = hat_note
                    dur  = 0.1
                elif open_hat_style == "offbeats" and abs(beat_frac - 0.5) < 0.01:
                    note = DRUM_MAP["open_hat"]
                    dur  = 0.2
                    close_t = t + 0.45
                    if close_t < bar_start + beats_per_bar:
                        close_tick = int(close_t * ticks_per_beat)
                        close_tick = apply_swing(close_tick, swing_amount, ticks_per_beat)
                        events.append(NoteEvent(
                            pitch=DRUM_MAP["closed_hat"],
                            start=close_tick / ticks_per_beat,
                            duration=0.03,
                            velocity=max(1, vel - 20),
                            channel=DRUM_CHANNEL,
                        ))
                elif use_planned_open and pos_key in open_hat_positions:
                    note = DRUM_MAP["open_hat"]
                    dur  = 0.35   # sustains until the kick closes it
                else:
                    note = hat_note
                    dur  = 0.06

                t_tick = int(t * ticks_per_beat)
                t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                events.append(NoteEvent(
                    pitch=note,
                    start=t_tick / ticks_per_beat + _jitter("hat", h),
                    duration=dur,
                    velocity=max(1, min(127, vel)),
                    channel=DRUM_CHANNEL,
                ))

        # EDM build: accelerating kick hits in last 2 beats
        if edm_build_active:
            for edm_b in [2.0, 2.5, 3.0, 3.5]:
                if not any(abs(edm_b - k) < 0.05 for k in kick_beats):
                    t = bar_start + edm_b
                    t_tick = int(t * ticks_per_beat)
                    t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                    events.append(NoteEvent(
                        pitch=DRUM_MAP["kick"],
                        start=t_tick / ticks_per_beat + _jitter("kick", h),
                        duration=0.1,
                        velocity=min(127, 92 + random.randint(-6, 6)),
                        channel=DRUM_CHANNEL,
                    ))

        # ── Ghost notes ───────────────────────────────────────────────────────
        if ghost_note_prob > 0 and not is_intro:
            main_positions = set()
            for b_f in [float(b) - 1.0 for b in snare_beats]:
                main_positions.add(round(b_f % beats_per_bar, 2))
            for b in kick_beats:
                main_positions.add(round(b, 2))

            secondary = SECONDARY_GHOSTS if bar_in_pair == 0 else {0.75, 1.25, 2.25, 3.25}

            for s in range(int(beats_per_bar / step)):
                beat_in_bar = round(s * step, 4)
                if round(beat_in_bar, 2) in main_positions:
                    continue
                pos = round(beat_in_bar, 2)
                if pos in PRIMARY_GHOSTS:
                    prob = ghost_note_prob * 0.65
                elif pos in secondary:
                    prob = ghost_note_prob * 0.22
                else:
                    prob = ghost_note_prob * 0.05
                if not should_trigger(prob):
                    continue

                t      = bar_start + beat_in_bar
                t_tick = int(t * ticks_per_beat)
                t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)

                # Velocity swell toward snare beats, scaled by humanize
                dist_to_snare = min(
                    abs(beat_in_bar - 1.0),
                    abs(beat_in_bar - 3.0),
                )
                prox = max(0.0, 1.0 - dist_to_snare)
                # Humanize expands the ghost velocity range for a looser feel
                ghost_lo  = int(18 + h * 6)
                ghost_hi  = int(42 + h * 14)
                ghost_vel = int(ghost_lo + prox * (ghost_hi - ghost_lo) * 0.85) + random.randint(-4, 4)
                events.append(NoteEvent(
                    pitch=DRUM_MAP["snare"],
                    start=t_tick / ticks_per_beat + _jitter("ghost", h),
                    duration=0.05,
                    velocity=max(ghost_lo, min(ghost_hi, ghost_vel)),
                    channel=DRUM_CHANNEL,
                ))

        # ── Fills ─────────────────────────────────────────────────────────────
        is_last_bar  = (bar == bars - 1) and not is_loop
        do_fill = (
            (tom_fills and bar % 4 == 3 and complexity > 0.3 and not is_last_bar)
            or (is_section_end and not is_last_bar)
        )
        # Outros wind down — no fill vocabulary, the section just decays
        if is_outro:
            do_fill = False

        # Size the section-boundary fill by the energy of what comes next: a fill
        # into a chorus hits hard, a fill into an outro barely registers.
        transition_scale = 1.0
        if is_section_end and next_energy is not None:
            transition_scale = 0.55 + 0.55 * next_energy
            if next_energy <= 0.35:
                do_fill = False   # heading into intro/outro energy: no tom flourish

        # Snare-roll build: always into a chorus (any style), plus wherever the
        # style asks for EDM-style drops at section ends.
        build_roll = (
            is_section_end and not is_last_bar and not is_outro and complexity > 0.2
            and next_section_type == "chorus"
        )

        if (edm_drops and is_section_end and not is_last_bar and complexity > 0.2) or build_roll:
            # Snare roll: 8 32nd notes from 3.5 → 4.0, velocity builds 52 → 120
            for r_i in range(8):
                r_start = bar_start + 3.5 + r_i * 0.0625
                r_vel   = min(127, 52 + r_i * 9 + random.randint(-4, 4))
                events.append(NoteEvent(
                    pitch=DRUM_MAP["snare"],
                    start=r_start + _jitter("snare", h),
                    duration=0.05,
                    velocity=r_vel,
                    channel=DRUM_CHANNEL,
                ))
        elif do_fill and mined_fills:
            # Data-driven fill mined from a real drummer (Groove MIDI). Layer its
            # toms / snares / crash across the bar; the kick/hat groove already
            # placed above keeps the pulse underneath.
            chosen = random.choice(mined_fills)
            fill_intensity = min(1.0, (0.7 + complexity * 0.25) * transition_scale)
            for entry in chosen:
                key, vel = entry[1], entry[2]
                if key not in _FILL_LAYER_KEYS or not should_trigger(fill_intensity):
                    continue
                fv = int(vel * phrase_dyn) + random.randint(-5, 5)
                events.append(NoteEvent(
                    pitch=DRUM_MAP[key],
                    start=bar_start + entry[0] * step + _jitter("fill", h),
                    duration=0.1,
                    velocity=min(127, max(1, fv)),
                    channel=DRUM_CHANNEL,
                ))

        elif do_fill:
            fill_intensity = min(1.0, (0.55 + complexity * 0.35) * transition_scale)

            # Micro fill (subtle): always precedes a big fill to signal it
            # — one soft snare accent 3 16ths before bar end, always present
            micro_start = bar_start + 3.25
            events.append(NoteEvent(
                pitch=DRUM_MAP["snare"],
                start=micro_start + _jitter("fill", h),
                duration=0.06,
                velocity=min(127, int((58 + random.randint(-6, 6)) * phrase_dyn)),
                channel=DRUM_CHANNEL,
            ))

            # Choose fill variant by complexity
            _FILL_VARIANTS = [
                # Level 1 — 2-hit sparse
                [(3.5,  "tom_mid", 74), (3.75, "tom_lo",  70)],
                # Level 2 — 3-hit cascade
                [(3.25, "tom_hi",  76), (3.5,  "tom_mid", 72), (3.75, "tom_lo",  68)],
                # Level 3 — classic 4-hit
                [(3.0,  "tom_hi",  74), (3.25, "tom_mid", 71), (3.5,  "tom_lo",  69), (3.75, "tom_lo",  66)],
                # Level 4 — 5-hit build
                [(2.75, "tom_hi",  67), (3.0,  "tom_hi",  71), (3.25, "tom_mid", 73), (3.5,  "tom_lo",  71), (3.75, "tom_lo",  68)],
                # Level 5 — reverse tom + snare crack
                [(3.0,  "tom_lo",  68), (3.25, "tom_mid", 71), (3.5,  "tom_hi",  75), (3.75, "snare",   90)],
                # Level 6 — flam into snare
                [(3.0,  "tom_hi",  70), (3.5,  "tom_lo",  68), (3.625, "snare",  66), (3.75, "snare",   96)],
                # Level 7 — snare run (no toms, subtle)
                [(3.5,  "snare",   72), (3.625, "snare",  80), (3.75, "snare",   92)],
            ]
            # Weight toward simpler fills at lower complexity
            weights = [
                max(0.05, 0.6 - complexity * 0.4),   # L1
                max(0.05, 0.5 - complexity * 0.2),   # L2
                0.18,                                  # L3 always medium
                complexity * 0.20,                     # L4 scaled
                complexity * 0.20,                     # L5 scaled
                complexity * 0.15,                     # L6 scaled
                0.12,                                  # L7 always present
            ]
            total_w = sum(weights)
            chosen_fill = random.choices(_FILL_VARIANTS, weights=[w / total_w for w in weights])[0]

            for b_offset, drum_key, base_vel in chosen_fill:
                if should_trigger(fill_intensity):
                    fill_vel = int(base_vel * phrase_dyn) + random.randint(-6, 6)
                    events.append(NoteEvent(
                        pitch=DRUM_MAP[drum_key],
                        start=bar_start + b_offset + _jitter("fill", h),
                        duration=0.1,
                        velocity=min(127, max(1, fill_vel)),
                        channel=DRUM_CHANNEL,
                    ))

        # ── Mid-phrase micro-variation ─────────────────────────────────────────
        # Without tom_fills a style otherwise repeats one groove verbatim for a
        # whole section — a real drummer instead marks the turn of each 4-bar
        # phrase with a tiny gesture. This adds a SUBTLE one (a ghost-snare
        # pickup or a kick push) on the last bar of each INTERIOR phrase. It is
        # deliberately smaller than a fill and excludes: the section-end bar
        # (which already gets the real transition fill), intros/outros (which
        # strip or decay), and tom_fills styles (already filling bar%4==3), so
        # the gesture never doubles up or competes with a boundary fill.
        if (bars >= 8 and bar % 4 == 3 and not is_section_end and not is_last_bar
                and not is_intro and not is_outro and not tom_fills
                and complexity > 0.25 and should_trigger(0.45 + variation * 0.3)):
            if should_trigger(0.66):
                # Ghost-snare pickup: two soft snares leaning over the barline.
                for _mo, _mv in ((3.5, 44), (3.75, 60)):
                    events.append(NoteEvent(
                        pitch=DRUM_MAP["snare"],
                        start=bar_start + _mo + _jitter("ghost", h),
                        duration=0.05,
                        velocity=max(1, min(127, int(_mv * phrase_dyn) + random.randint(-5, 5))),
                        channel=DRUM_CHANNEL,
                    ))
            else:
                # Kick push: an extra kick on the "and of 4" nudging the turn.
                events.append(NoteEvent(
                    pitch=DRUM_MAP["kick"],
                    start=bar_start + 3.5 + _jitter("kick", h),
                    duration=0.1,
                    velocity=max(1, min(127, int(82 * phrase_dyn) + random.randint(-6, 6))),
                    channel=DRUM_CHANNEL,
                ))

        # ── Percussion layers ─────────────────────────────────────────────────
        if "shaker" in perc_layers:
            for s in [i * 0.5 for i in range(8)]:
                if not should_trigger(0.80):
                    continue
                t_tick = int((bar_start + s) * ticks_per_beat)
                t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                is_down = s % 1.0 < 0.01
                vel_s = int((52 if is_down else 40) * phrase_dyn) + random.randint(-8, 8)
                events.append(NoteEvent(
                    pitch=DRUM_MAP["perc1"],
                    start=t_tick / ticks_per_beat + _jitter("perc", h),
                    duration=0.08,
                    velocity=max(1, min(127, vel_s)),
                    channel=DRUM_CHANNEL,
                ))

        if "tambourine" in perc_layers:
            for tamb_b in [1.0, 3.0]:
                t_tick = int((bar_start + tamb_b) * ticks_per_beat)
                t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                tamb_vel = int((60 + random.randint(-10, 10)) * phrase_dyn)
                events.append(NoteEvent(
                    pitch=DRUM_MAP["perc2"],
                    start=t_tick / ticks_per_beat + _jitter("perc", h),
                    duration=0.06,
                    velocity=max(1, min(127, tamb_vel)),
                    channel=DRUM_CHANNEL,
                ))
            if complexity > 0.45 and should_trigger(0.4):
                off_b  = random.choice([0.5, 2.5])
                t_tick = int((bar_start + off_b) * ticks_per_beat)
                t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                events.append(NoteEvent(
                    pitch=DRUM_MAP["perc2"],
                    start=t_tick / ticks_per_beat + _jitter("perc", h),
                    duration=0.06,
                    velocity=max(1, min(127, int((46 + random.randint(-8, 8)) * phrase_dyn))),
                    channel=DRUM_CHANNEL,
                ))

    # No final bulk jitter — per-instrument jitter applied at generation time
    return events


def _vary_kick_beats_bar2(kick_beats: list, complexity: float) -> list:
    """Return a rhythmically varied kick list for bar 2 of a 2-bar phrase."""
    beats = list(kick_beats)
    r = random.random()
    if r < 0.28:
        if 3.75 not in beats:
            beats.append(3.75)
    elif r < 0.48 and complexity > 0.35:
        if 1.75 not in beats:
            beats.append(1.75)
    elif r < 0.62 and complexity > 0.50:
        extras = [b for b in [2.5, 2.75] if b not in beats]
        if extras:
            beats.append(random.choice(extras))
    elif r < 0.73 and len(beats) > 2:
        removable = [b for b in beats if b > 0.15]
        if removable:
            beats.remove(random.choice(removable))
    elif r < 0.84 and complexity > 0.60:
        for b in [1.75, 3.75]:
            if b not in beats:
                beats.append(b)
    return sorted(beats)
