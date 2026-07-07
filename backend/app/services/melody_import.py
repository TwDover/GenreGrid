# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Build a song around a user's melody: parse an uploaded MIDI file, detect its
key, and derive a chord progression that supports it. The melody becomes the
song's chorus hook; the rest of the arrangement is generated around it."""
import io
import math

import mido

from app.core.constants import TICKS_PER_BEAT, NOTE_NAMES
from app.services.midi_writer import NoteEvent
from app.theory.chords import roman_to_chord


# Krumhansl-Kessler key profiles: perceptual weight of each scale degree.
_KK_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_KK_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

# Diatonic chord vocabulary per mode, in rough preference order (ties break
# toward the front, which favors tonic-function harmony).
_MINOR_CHORDS = ["i", "VI", "iv", "VII", "III", "v"]
_MAJOR_CHORDS = ["I", "vi", "IV", "V", "ii", "iii"]


def parse_melody_midi(data: bytes) -> tuple[list[NoteEvent], float | None]:
    """Parse uploaded MIDI bytes → (melody NoteEvents, file bpm or None).

    Picks the most melody-like track (non-percussion, preferring the higher
    average pitch among tracks with a reasonable note count), pairs note_on/off
    into durations, and normalizes timing so the melody starts in bar 1 while
    keeping its position within the bar.
    """
    mid = mido.MidiFile(file=io.BytesIO(data))
    tpb = mid.ticks_per_beat or TICKS_PER_BEAT

    bpm: float | None = None
    tracks: list[list[NoteEvent]] = []
    for track in mid.tracks:
        abs_t = 0
        open_notes: dict[tuple[int, int], tuple[int, int]] = {}   # (ch, pitch) -> (start_tick, vel)
        notes: list[NoteEvent] = []
        for msg in track:
            abs_t += msg.time
            if msg.type == "set_tempo" and bpm is None:
                bpm = mido.tempo2bpm(msg.tempo)
            elif msg.type == "note_on" and msg.velocity > 0 and msg.channel != 9:
                open_notes[(msg.channel, msg.note)] = (abs_t, msg.velocity)
            elif msg.type in ("note_off", "note_on") and (msg.type == "note_off" or msg.velocity == 0):
                key = (getattr(msg, "channel", 0), getattr(msg, "note", -1))
                if key in open_notes:
                    start_tick, vel = open_notes.pop(key)
                    dur = max(1, abs_t - start_tick)
                    notes.append(NoteEvent(key[1], start_tick / tpb, dur / tpb, vel, 2))
        if notes:
            tracks.append(notes)

    if not tracks:
        return [], bpm

    # Most melody-like track: enough notes to be a line, then highest average pitch
    substantial = [t for t in tracks if len(t) >= 8] or tracks
    melody = max(substantial, key=lambda t: sum(n.pitch for n in t) / len(t))
    melody.sort(key=lambda n: n.start)

    # Normalize: drop leading empty bars but keep the melody's position in its bar
    first = melody[0].start
    shift = math.floor(first / 4) * 4
    return [NoteEvent(n.pitch, n.start - shift, n.duration, n.velocity, 2) for n in melody], bpm


def detect_key(notes: list[NoteEvent]) -> tuple[str, str]:
    """Krumhansl-Schmuckler key detection → (key name, "major"|"minor").

    Correlates the melody's duration-weighted pitch-class histogram against the
    24 rotated Krumhansl-Kessler profiles and returns the best match.
    """
    if not notes:
        return "C", "minor"
    hist = [0.0] * 12
    for n in notes:
        hist[n.pitch % 12] += n.duration

    def _corr(profile: list[float], rotation: int) -> float:
        rotated = [hist[(i + rotation) % 12] for i in range(12)]
        mx = sum(rotated) / 12
        my = sum(profile) / 12
        num = sum((rotated[i] - mx) * (profile[i] - my) for i in range(12))
        den = math.sqrt(sum((rotated[i] - mx) ** 2 for i in range(12))
                        * sum((profile[i] - my) ** 2 for i in range(12)))
        return num / den if den > 1e-9 else 0.0

    best = ("C", "minor", -2.0)
    for root in range(12):
        for profile, mode in ((_KK_MAJOR, "major"), (_KK_MINOR, "minor")):
            score = _corr(profile, root)
            if score > best[2]:
                best = (NOTE_NAMES[root], mode, score)
    return best[0], best[1]


def derive_progression(notes: list[NoteEvent], key: str, scale: str,
                       length: int = 4) -> list[str]:
    """Derive a supporting chord progression from the melody, one chord per bar.

    Each bar picks the diatonic chord whose tones best cover the bar's melody
    (duration-weighted, downbeats double). The first bar prefers the tonic so
    the loop grounds itself; the result is trimmed/padded to `length` chords
    and reused across the whole song by the builder.
    """
    candidates = _MINOR_CHORDS if scale != "major" else _MAJOR_CHORDS
    chord_pcs = {r: {p % 12 for p in roman_to_chord(r, key, scale, octave=4)} for r in candidates}

    total_bars = max(1, math.ceil(max((n.start + n.duration) for n in notes) / 4)) if notes else length
    progression: list[str] = []
    for bar in range(min(total_bars, length)):
        lo, hi = bar * 4, (bar + 1) * 4
        weights: dict[int, float] = {}
        for n in notes:
            if lo <= n.start < hi:
                w = n.duration * (2.0 if (n.start % 1.0) < 0.13 else 1.0)
                weights[n.pitch % 12] = weights.get(n.pitch % 12, 0.0) + w
        if not weights:
            progression.append(progression[-1] if progression else candidates[0])
            continue
        total_w = sum(weights.values())

        def _score(roman: str) -> float:
            cover = sum(w for pc, w in weights.items() if pc in chord_pcs[roman]) / total_w
            pref = (len(candidates) - candidates.index(roman)) * 0.01   # mild tonic-function bias
            tonic_bonus = 0.08 if bar == 0 and roman == candidates[0] else 0.0
            return cover + pref + tonic_bonus

        progression.append(max(candidates, key=_score))

    base = list(progression) or [candidates[0]]
    while len(progression) < length:
        progression.append(base[len(progression) % len(base)])
    return progression[:length]


def fit_melody_to_bars(notes: list[NoteEvent], bars: int) -> list[NoteEvent]:
    """Loop or trim a melody so it exactly fills `bars` (used to place the user's
    hook into a chorus of fixed length)."""
    if not notes:
        return []
    limit = bars * 4.0
    span_bars = max(1, math.ceil(max(n.start + n.duration for n in notes) / 4))
    span = span_bars * 4.0
    out: list[NoteEvent] = []
    offset = 0.0
    while offset < limit - 0.01:
        for n in notes:
            t = n.start + offset
            if t < limit - 0.05:
                out.append(NoteEvent(n.pitch, t, min(n.duration, limit - t), n.velocity, n.channel))
        offset += span
    return out
