import random
from typing import List

from app.services.midi_writer import NoteEvent
from app.core.constants import DRUM_MAP, DRUM_CHANNEL
from app.services.variation import should_trigger
from app.theory.rhythm import apply_swing


def generate_drums(
    style: dict,
    bars: int,
    complexity: float,
    variation: float,
) -> List[NoteEvent]:
    events: List[NoteEvent] = []
    drum_cfg = style.get("drums", {})

    hat_density = drum_cfg.get("hat_density", 0.7)
    triplet_prob = drum_cfg.get("triplet_probability", 0.2)
    snare_beats = drum_cfg.get("snare_standard_beats", [2, 4])
    swing_amount = drum_cfg.get("swing", 0.0)
    use_ride = drum_cfg.get("use_ride", False)
    use_clap = drum_cfg.get("use_clap", False)
    crash_on_bar_1 = drum_cfg.get("crash_on_bar_1", False)
    tom_fills = drum_cfg.get("tom_fills", False)

    hat_note = DRUM_MAP["ride"] if use_ride else DRUM_MAP["closed_hat"]

    beats_per_bar = 4
    step = 0.25
    ticks_per_beat = 480

    for bar in range(bars):
        bar_start = bar * beats_per_bar

        # Crash on bar 1 and at phrase boundaries when complexity is high
        if crash_on_bar_1 and (bar == 0 or (complexity > 0.7 and bar % 4 == 0)):
            events.append(NoteEvent(
                pitch=DRUM_MAP["crash"],
                start=bar_start,
                duration=0.5,
                velocity=100 + random.randint(-8, 8),
                channel=DRUM_CHANNEL,
            ))

        # Kick: use style kick_pattern if present, otherwise fall back to generic logic
        kick_pattern = drum_cfg.get("kick_pattern")
        if kick_pattern:
            kick_beats = [
                i * step for i, on in enumerate(kick_pattern)
                if on and should_trigger(0.88 + variation * 0.1)
            ]
            # Always guarantee beat 1
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

        for b in kick_beats:
            t = bar_start + b
            t_tick = int(t * ticks_per_beat)
            t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
            events.append(NoteEvent(
                pitch=DRUM_MAP["kick"],
                start=t_tick / ticks_per_beat,
                duration=0.1,
                velocity=100 + random.randint(-8, 8),
                channel=DRUM_CHANNEL,
            ))

        # Snare
        for snare_b in snare_beats:
            b_f = float(snare_b) - 1.0
            t = bar_start + b_f
            t_tick = int(t * ticks_per_beat)
            t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
            events.append(NoteEvent(
                pitch=DRUM_MAP["snare"],
                start=t_tick / ticks_per_beat,
                duration=0.1,
                velocity=90 + random.randint(-10, 10),
                channel=DRUM_CHANNEL,
            ))

        # Clap layered on snare beats
        if use_clap:
            for snare_b in snare_beats:
                b_f = float(snare_b) - 1.0
                t = bar_start + b_f
                t_tick = int(t * ticks_per_beat)
                t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                events.append(NoteEvent(
                    pitch=DRUM_MAP["clap"],
                    start=t_tick / ticks_per_beat,
                    duration=0.05,
                    velocity=85 + random.randint(-10, 10),
                    channel=DRUM_CHANNEL,
                ))

        # Hi-hats or ride
        use_triplet = should_trigger(triplet_prob)
        if use_triplet:
            hat_steps = [i / 3.0 for i in range(bars * 12)]
            hat_steps = [s for s in hat_steps if bar_start <= s < bar_start + beats_per_bar]
        else:
            hat_steps = [bar_start + i * step for i in range(int(beats_per_bar / step))]

        for t in hat_steps:
            if not should_trigger(hat_density * (0.7 + complexity * 0.3)):
                continue
            if use_ride:
                note = hat_note
                dur = 0.1
            else:
                is_open = should_trigger(0.1)
                note = DRUM_MAP["open_hat"] if is_open else hat_note
                dur = 0.2 if is_open else 0.05
            t_tick = int(t * ticks_per_beat)
            t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
            vel = 60 + random.randint(-15, 15)
            events.append(NoteEvent(
                pitch=note,
                start=t_tick / ticks_per_beat,
                duration=dur,
                velocity=vel,
                channel=DRUM_CHANNEL,
            ))

        # Ghost notes: quiet snare hits on off-16th positions (swing-derived probability)
        ghost_note_prob = drum_cfg.get("ghost_note_prob", swing_amount * 0.8 if swing_amount >= 0.3 else 0.0)
        if ghost_note_prob > 0:
            main_positions = set()
            for b_f in [float(b) - 1.0 for b in snare_beats]:
                main_positions.add(round(b_f % beats_per_bar, 2))
            for b in kick_beats:
                main_positions.add(round(b, 2))

            for s in range(int(beats_per_bar / step)):
                beat_in_bar = s * step
                if round(beat_in_bar, 2) in main_positions:
                    continue
                # Prefer "e" and "ah" sub-positions (beat+0.25, beat+0.75)
                pos_in_beat = round(beat_in_bar % 1.0, 2)
                is_preferred = pos_in_beat in (0.25, 0.75)
                prob = ghost_note_prob * (0.35 if is_preferred else 0.12)
                if not should_trigger(prob):
                    continue
                t = bar_start + beat_in_bar
                t_tick = int(t * ticks_per_beat)
                t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
                events.append(NoteEvent(
                    pitch=DRUM_MAP["snare"],
                    start=t_tick / ticks_per_beat,
                    duration=0.05,
                    velocity=random.randint(22, 36),
                    channel=DRUM_CHANNEL,
                ))

        # Tom fill on beat 4 of the last bar in every 4-bar phrase
        if tom_fills and bar % 4 == 3 and complexity > 0.3:
            for b_offset, tom_note, base_vel in [
                (3.0,  DRUM_MAP["tom_hi"],  75),
                (3.25, DRUM_MAP["tom_mid"], 72),
                (3.5,  DRUM_MAP["tom_lo"],  70),
                (3.75, DRUM_MAP["tom_lo"],  68),
            ]:
                if should_trigger(0.6 + complexity * 0.3):
                    events.append(NoteEvent(
                        pitch=tom_note,
                        start=bar_start + b_offset,
                        duration=0.1,
                        velocity=base_vel + random.randint(-8, 8),
                        channel=DRUM_CHANNEL,
                    ))

    return events
