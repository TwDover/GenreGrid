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

    beats_per_bar = 4
    step = 0.25  # 16th note grid
    ticks_per_beat = 480

    for bar in range(bars):
        bar_start = bar * beats_per_bar

        # Kick: beat 1, sometimes beat 3, complexity adds offbeats
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
            b_f = float(snare_b) - 1.0  # convert 1-indexed beat number to 0-indexed
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

        # Hi-hats
        use_triplet = should_trigger(triplet_prob)
        if use_triplet:
            hat_steps = [i / 3.0 for i in range(bars * 12)]  # triplet 8ths
            hat_steps = [s for s in hat_steps if bar_start <= s < bar_start + beats_per_bar]
        else:
            hat_steps = [bar_start + i * step for i in range(int(beats_per_bar / step))]

        for t in hat_steps:
            if not should_trigger(hat_density * (0.7 + complexity * 0.3)):
                continue
            is_open = should_trigger(0.1)
            t_tick = int(t * ticks_per_beat)
            t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
            vel = 60 + random.randint(-15, 15)
            events.append(NoteEvent(
                pitch=DRUM_MAP["open_hat"] if is_open else DRUM_MAP["closed_hat"],
                start=t_tick / ticks_per_beat,
                duration=0.05 if not is_open else 0.2,
                velocity=vel,
                channel=DRUM_CHANNEL,
            ))

    return events
