import random
from typing import List

from app.services.midi_writer import NoteEvent
from app.core.constants import DRUM_MAP, DRUM_CHANNEL
from app.services.variation import should_trigger
from app.services.humanize import micro_jitter
from app.theory.rhythm import apply_swing


def generate_drums(
    style: dict,
    bars: int,
    complexity: float,
    variation: float,
    section_end_bars: list[int] | None = None,
    is_loop: bool = False,
) -> List[NoteEvent]:
    events: List[NoteEvent] = []
    drum_cfg = style.get("drums", {})

    hat_density     = drum_cfg.get("hat_density", 0.7)
    triplet_prob    = drum_cfg.get("triplet_probability", 0.2)
    snare_beats     = drum_cfg.get("snare_standard_beats", [2, 4])
    swing_amount    = drum_cfg.get("swing", 0.0)
    use_ride        = drum_cfg.get("use_ride", False)
    use_clap        = drum_cfg.get("use_clap", False)
    crash_on_bar_1  = drum_cfg.get("crash_on_bar_1", False)
    tom_fills       = drum_cfg.get("tom_fills", False)
    # hat_roll_prob: probability of replacing an 8th-note hat with a 3x 32nd-note burst (trap rolls)
    hat_roll_prob     = drum_cfg.get("hat_roll_prob", 0.0)
    # open_hat_style: "random" (legacy) | "offbeats" (intentional off-beat open hats, house/funk)
    open_hat_style    = drum_cfg.get("open_hat_style", "random")
    # snare_upbeat_prob: add a snare hit on the 8th-note before beats 2 and 4 ("and of 1" / "and of 3")
    snare_upbeat_prob = drum_cfg.get("snare_upbeat_prob", 0.0)
    # snare_beat3_prob: occasional snare on beat 3 (differentiates funk/soul from straight 2-and-4)
    snare_beat3_prob  = drum_cfg.get("snare_beat3_prob", 0.0)
    # ghost_note_prob: explicit override; defaults from swing like before
    ghost_note_prob = drum_cfg.get(
        "ghost_note_prob",
        swing_amount * 0.8 if swing_amount >= 0.3 else 0.0,
    )
    ride_style = drum_cfg.get("ride_style", "default")
    edm_drops = drum_cfg.get("edm_drops", False)

    perc_layers  = drum_cfg.get("perc_layers", [])
    section_ends = set(section_end_bars) if section_end_bars else set()

    hat_note = DRUM_MAP["ride"] if use_ride else DRUM_MAP["closed_hat"]

    beats_per_bar = 4
    step          = 0.25    # sixteenth note
    ticks_per_beat = 480

    # Decide hat subdivision mode once per 4-bar phrase so the groove stays consistent.
    phrase_hat_modes: dict[int, bool] = {}
    for bar in range(bars):
        phrase_idx = bar // 4
        if phrase_idx not in phrase_hat_modes:
            phrase_hat_modes[phrase_idx] = should_trigger(triplet_prob)

    # Primary ghost note positions (4th 16th of beats 2 and 4) — most musical per research
    PRIMARY_GHOSTS   = {1.75, 3.75}
    # Secondary: other "e" and "a" 16th subdivisions
    SECONDARY_GHOSTS = {0.25, 0.75, 1.25, 2.25, 2.75, 3.25}

    for bar in range(bars):
        bar_start    = bar * beats_per_bar
        bar_in_pair  = bar % 2   # 0 = first bar of 2-bar phrase, 1 = second
        bar_in_8     = bar % 8
        # At bar 4 of every 8-bar phrase: "breath" — reduce hat density
        hat_breath   = 0.70 if bar_in_8 == 4 else 1.0

        # Hi-hat velocity breathing: builds from 0.85 → 1.0 across a 4-bar phrase, then resets
        breath_scale = 0.85 + 0.15 * ((bar % 4) / 4.0)

        # ── Crash ──────────────────────────────────────────────────────────────
        if crash_on_bar_1 and (bar == 0 or (complexity > 0.7 and bar % 4 == 0)):
            events.append(NoteEvent(
                pitch=DRUM_MAP["crash"],
                start=bar_start,
                duration=0.5,
                velocity=100 + random.randint(-8, 8),
                channel=DRUM_CHANNEL,
            ))

        # ── Kick ───────────────────────────────────────────────────────────────
        kick_pattern = drum_cfg.get("kick_pattern")
        if kick_pattern:
            kick_beats = [
                i * step for i, on in enumerate(kick_pattern)
                if on and should_trigger(0.88 + variation * 0.1)
            ]
            if not any(b < step for b in kick_beats):
                kick_beats.insert(0, 0.0)
        else:
            kick_beats = [0.0]
            if complexity > 0.4:
                kick_beats.append(2.0)
            if complexity > 0.7 and should_trigger(0.5):
                kick_beats.append(2.5)
            if should_trigger(variation * 0.3):
                kick_beats.append(0.75)

        # Two-bar variation: bar 2 adds a syncopated kick anticipating beat 3
        if bar_in_pair == 1 and complexity > 0.5 and should_trigger(0.4):
            if 1.75 not in kick_beats:
                kick_beats.append(1.75)

        for b in kick_beats:
            t      = bar_start + b
            t_tick = int(t * ticks_per_beat)
            t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
            beat_in_bar = round(b % beats_per_bar, 4)
            if beat_in_bar < 0.01:
                kick_vel = 108 + random.randint(-6, 6)
            elif abs(beat_in_bar - 2.0) < 0.01:
                kick_vel = 96 + random.randint(-8, 8)
            else:
                kick_vel = 88 + random.randint(-10, 10)
            events.append(NoteEvent(
                pitch=DRUM_MAP["kick"],
                start=t_tick / ticks_per_beat,
                duration=0.1,
                velocity=min(127, kick_vel),
                channel=DRUM_CHANNEL,
            ))

        # ── Snare — research-backed velocity: 100–110 ─────────────────────────
        for snare_b in snare_beats:
            b_f    = float(snare_b) - 1.0
            t      = bar_start + b_f
            t_tick = int(t * ticks_per_beat)
            t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
            events.append(NoteEvent(
                pitch=DRUM_MAP["snare"],
                start=t_tick / ticks_per_beat,
                duration=0.1,
                velocity=103 + random.randint(-8, 8),
                channel=DRUM_CHANNEL,
            ))

        # Dynamic upbeat snares: hit on the 8th note before beats 2 & 4
        if snare_upbeat_prob > 0:
            for upbeat_b in [0.5, 2.5]:   # "and of 1" and "and of 3"
                if should_trigger(snare_upbeat_prob):
                    t = bar_start + upbeat_b
                    t_tick = int(t * ticks_per_beat)
                    t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                    events.append(NoteEvent(
                        pitch=DRUM_MAP["snare"],
                        start=t_tick / ticks_per_beat,
                        duration=0.1,
                        velocity=min(127, 72 + random.randint(-8, 8)),
                        channel=DRUM_CHANNEL,
                    ))

        # Beat-3 snare: occasional hit on beat 3 for funk/soul syncopation
        if snare_beat3_prob > 0 and should_trigger(snare_beat3_prob):
            t = bar_start + 2.0   # beat 3 (0-indexed)
            t_tick = int(t * ticks_per_beat)
            t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
            events.append(NoteEvent(
                pitch=DRUM_MAP["snare"],
                start=t_tick / ticks_per_beat,
                duration=0.1,
                velocity=min(127, 80 + random.randint(-10, 10)),
                channel=DRUM_CHANNEL,
            ))

        # Clap layered on snare beats
        if use_clap:
            for snare_b in snare_beats:
                b_f    = float(snare_b) - 1.0
                t      = bar_start + b_f
                t_tick = int(t * ticks_per_beat)
                t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                events.append(NoteEvent(
                    pitch=DRUM_MAP["clap"],
                    start=t_tick / ticks_per_beat,
                    duration=0.05,
                    velocity=88 + random.randint(-8, 8),
                    channel=DRUM_CHANNEL,
                ))

        # ── Hi-hats / ride ────────────────────────────────────────────────────
        use_triplet = phrase_hat_modes[bar // 4]
        if use_triplet:
            hat_steps = [i / 3.0 for i in range(bars * 12)]
            hat_steps = [s for s in hat_steps if bar_start <= s < bar_start + beats_per_bar]
        else:
            hat_steps = [bar_start + i * step for i in range(int(beats_per_bar / step))]

        # EDM drop build: last bar before section change strips hats and rolls kick
        is_section_end = bar in section_ends
        edm_build_active = edm_drops and is_section_end and complexity > 0.4

        # Track 16th positions already filled by a roll so we skip them
        rolled_positions: set[float] = set()

        if use_ride and ride_style == "jazz":
            # Classic "spang-a-lang" jazz ride pattern: quarter notes + swing 8ths
            # Plus hi-hat "chick" on beats 2 and 4
            _JAZZ_RIDE = [1, 0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 1, 0, 0, 0]  # 16th positions
            for s, on in enumerate(_JAZZ_RIDE):
                if not on:
                    continue
                t = bar_start + s * step
                beat_frac = round(s * step % 1.0, 4)
                # Downbeats louder, off-beats softer
                base_v = 64 if beat_frac < 0.01 else (52 if abs(beat_frac - 0.5) < 0.01 else 44)
                vel = int(base_v * breath_scale) + random.randint(-5, 5)
                t_tick = int(t * ticks_per_beat)
                t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                events.append(NoteEvent(
                    pitch=DRUM_MAP["ride"],
                    start=t_tick / ticks_per_beat,
                    duration=0.1,
                    velocity=max(1, min(127, vel)),
                    channel=DRUM_CHANNEL,
                ))
            # Hi-hat "chick" on beats 2 and 4 (positions 4 and 12 in 16th grid)
            for chick_b in [1.0, 3.0]:
                t = bar_start + chick_b
                t_tick = int(t * ticks_per_beat)
                t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                events.append(NoteEvent(
                    pitch=DRUM_MAP["closed_hat"],
                    start=t_tick / ticks_per_beat,
                    duration=0.04,
                    velocity=max(1, min(127, 55 + random.randint(-8, 8))),
                    channel=DRUM_CHANNEL,
                ))
        else:
            for t in hat_steps:
                # Suppress hats from beat 2 onward during EDM builds
                if edm_build_active and (t - bar_start) >= 1.5:
                    continue

                if not should_trigger(hat_density * hat_breath * (0.7 + complexity * 0.3)):
                    continue

                beat_frac = round((t - bar_start) % 1.0, 4)
                pos_key   = round(t - bar_start, 4)

                if pos_key in rolled_positions:
                    continue

                is_eighth = beat_frac < 0.01 or abs(beat_frac - 0.5) < 0.01

                # Velocity with breathing (on-beat / off-beat / 16th subdivision)
                if beat_frac < 0.01:
                    base_vel = 72
                elif abs(beat_frac - 0.5) < 0.01:
                    base_vel = 62
                else:
                    base_vel = 50
                vel = int(base_vel * breath_scale) + random.randint(-6, 6)

                # Trap hi-hat roll: replace 8th-note hit with 3x 32nd notes
                if hat_roll_prob > 0 and is_eighth and not use_ride and should_trigger(hat_roll_prob):
                    for r_i, r_offset in enumerate([0.0, 0.125, 0.25]):
                        r_t    = t + r_offset
                        r_tick = int(r_t * ticks_per_beat)
                        r_tick = apply_swing(r_tick, swing_amount, ticks_per_beat)
                        # Middle note of the roll is ~12 velocity lower
                        r_vel  = vel - (12 if r_i == 1 else 0)
                        events.append(NoteEvent(
                            pitch=DRUM_MAP["closed_hat"],
                            start=r_tick / ticks_per_beat,
                            duration=0.05,
                            velocity=max(1, min(127, r_vel)),
                            channel=DRUM_CHANNEL,
                        ))
                    # The 32nd note at +0.25 covers the next 16th step — skip it
                    rolled_positions.add(round(pos_key + 0.25, 4))
                    continue

                # Open hat logic
                if use_ride:
                    note = hat_note
                    dur  = 0.1
                elif open_hat_style == "offbeats" and abs(beat_frac - 0.5) < 0.01:
                    # Intentional open hat on 8th-note off-beats (house/funk feel)
                    note = DRUM_MAP["open_hat"]
                    dur  = 0.2
                    # Close it just before the next on-beat kick
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
                else:
                    is_open = should_trigger(0.08)
                    note    = DRUM_MAP["open_hat"] if is_open else hat_note
                    dur     = 0.2 if is_open else 0.05

                t_tick = int(t * ticks_per_beat)
                t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                events.append(NoteEvent(
                    pitch=note,
                    start=t_tick / ticks_per_beat,
                    duration=dur,
                    velocity=max(1, min(127, vel)),
                    channel=DRUM_CHANNEL,
                ))

        # EDM kick build: accelerating 8th notes in last 2 beats
        if edm_build_active:
            for edm_b in [2.0, 2.5, 3.0, 3.5]:
                t = bar_start + edm_b
                if not any(abs(k - edm_b) < 0.05 for k in kick_beats):  # don't double up
                    t_tick = int(t * ticks_per_beat)
                    t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                    events.append(NoteEvent(
                        pitch=DRUM_MAP["kick"],
                        start=t_tick / ticks_per_beat,
                        duration=0.1,
                        velocity=min(127, 94 + random.randint(-6, 6)),
                        channel=DRUM_CHANNEL,
                    ))

        # ── Ghost notes ───────────────────────────────────────────────────────
        if ghost_note_prob > 0:
            main_positions = set()
            for b_f in [float(b) - 1.0 for b in snare_beats]:
                main_positions.add(round(b_f % beats_per_bar, 2))
            for b in kick_beats:
                main_positions.add(round(b, 2))

            # Two-bar variation: bar 2 uses a shifted secondary set
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
                # Velocity swell: ghosts get louder closer to snare beats (2 and 4)
                # dist_to_snare: 0.0 = right next to snare, 1.0+ = far away
                dist_to_snare = min(
                    abs(beat_in_bar - 1.0),  # distance to beat 2 (0-indexed)
                    abs(beat_in_bar - 3.0),  # distance to beat 4 (0-indexed)
                )
                prox = max(0.0, 1.0 - dist_to_snare)   # 1.0 = adjacent to snare
                ghost_vel = int(26 + prox * 20) + random.randint(-4, 4)
                events.append(NoteEvent(
                    pitch=DRUM_MAP["snare"],
                    start=t_tick / ticks_per_beat,
                    duration=0.05,
                    velocity=max(18, min(52, ghost_vel)),
                    channel=DRUM_CHANNEL,
                ))

        # ── Fills: tom fill every 4 bars, snare roll at EDM section boundaries ──
        # In loop mode the final bar IS a section boundary we want to fill — it
        # leads back to bar 0 on the next iteration, so a fill sounds intentional.
        is_last_bar = (bar == bars - 1) and not is_loop
        do_fill = (tom_fills and bar % 4 == 3 and complexity > 0.3 and not is_last_bar) or (is_section_end and not is_last_bar)

        if edm_drops and is_section_end and not is_last_bar and complexity > 0.2:
            # Snare roll: 8 32nd notes from beat 3.5 → 4.0, velocity builds 52→120
            for r_i in range(8):
                r_start = bar_start + 3.5 + r_i * 0.0625
                r_vel = min(127, 52 + r_i * 9 + random.randint(-4, 4))
                events.append(NoteEvent(
                    pitch=DRUM_MAP["snare"],
                    start=r_start,
                    duration=0.05,
                    velocity=r_vel,
                    channel=DRUM_CHANNEL,
                ))
        elif do_fill:
            # Tom fill — choose a variant each time for variety
            fill_intensity = 0.6 + complexity * 0.3
            # Each entry: (beat_offset, drum_key, base_velocity)
            _FILL_VARIANTS = [
                # 2-hit sparse
                [(3.5,  "tom_mid", 76), (3.75, "tom_lo",  72)],
                # 3-hit cascade
                [(3.25, "tom_hi",  78), (3.5,  "tom_mid", 74), (3.75, "tom_lo",  70)],
                # 4-hit cascade (classic)
                [(3.0,  "tom_hi",  75), (3.25, "tom_mid", 72), (3.5,  "tom_lo",  70), (3.75, "tom_lo",  68)],
                # 5-hit build
                [(2.75, "tom_hi",  68), (3.0,  "tom_hi",  72), (3.25, "tom_mid", 74), (3.5,  "tom_lo",  72), (3.75, "tom_lo",  70)],
                # Reverse: lo → hi → snare accent
                [(3.0,  "tom_lo",  70), (3.25, "tom_mid", 72), (3.5,  "tom_hi",  76), (3.75, "snare",   88)],
                # Flam: stagger into snare crack
                [(3.0,  "tom_hi",  72), (3.5,  "tom_lo",  70), (3.625, "snare",   68), (3.75, "snare",  96)],
            ]
            chosen_fill = random.choice(_FILL_VARIANTS)
            for b_offset, drum_key, base_vel in chosen_fill:
                if should_trigger(fill_intensity):
                    events.append(NoteEvent(
                        pitch=DRUM_MAP[drum_key],
                        start=bar_start + b_offset,
                        duration=0.1,
                        velocity=min(127, base_vel + random.randint(-6, 6)),
                        channel=DRUM_CHANNEL,
                    ))

        # ── Percussion layers (shaker, tambourine) ────────────────────────────
        if "shaker" in perc_layers:
            # Shaker: 8th-note pulse, soft, throughout bar
            shaker_steps = [i * 0.5 for i in range(8)]
            for s in shaker_steps:
                if not should_trigger(0.80):
                    continue
                t_tick = int((bar_start + s) * ticks_per_beat)
                t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                is_downbeat_s = s % 1.0 < 0.01
                vel_s = (52 if is_downbeat_s else 40) + random.randint(-8, 8)
                events.append(NoteEvent(
                    pitch=DRUM_MAP["perc1"],
                    start=t_tick / ticks_per_beat,
                    duration=0.08,
                    velocity=max(1, min(127, vel_s)),
                    channel=DRUM_CHANNEL,
                ))

        if "tambourine" in perc_layers:
            # Tambourine: on beats 2 and 4 (snare positions), with occasional 8th off-beat
            for tamb_b in [1.0, 3.0]:
                t_tick = int((bar_start + tamb_b) * ticks_per_beat)
                t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                events.append(NoteEvent(
                    pitch=DRUM_MAP["perc2"],
                    start=t_tick / ticks_per_beat,
                    duration=0.06,
                    velocity=60 + random.randint(-10, 10),
                    channel=DRUM_CHANNEL,
                ))
            # Occasional 8th-note off-beat tambourine hit
            if complexity > 0.45 and should_trigger(0.4):
                off_b = random.choice([0.5, 2.5])
                t_tick = int((bar_start + off_b) * ticks_per_beat)
                t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                events.append(NoteEvent(
                    pitch=DRUM_MAP["perc2"],
                    start=t_tick / ticks_per_beat,
                    duration=0.06,
                    velocity=46 + random.randint(-8, 8),
                    channel=DRUM_CHANNEL,
                ))

    # Apply micro timing jitter to every drum hit to remove quantization feel
    return [
        NoteEvent(e.pitch, max(0.0, e.start + micro_jitter()), e.duration, e.velocity, e.channel)
        for e in events
    ]
