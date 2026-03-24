"""Translate NoteEvent lists into .mid files using mido."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import mido

from app.core.constants import TICKS_PER_BEAT, DRUM_CHANNEL


@dataclass
class NoteEvent:
    pitch: int
    start: float       # in beats (float)
    duration: float    # in beats (float)
    velocity: int
    channel: int = 0


def _events_to_track(events: List[NoteEvent], ticks_per_beat: int = TICKS_PER_BEAT) -> mido.MidiTrack:
    track = mido.MidiTrack()
    messages = []

    for ev in events:
        start_tick = int(ev.start * ticks_per_beat)
        end_tick = int((ev.start + ev.duration) * ticks_per_beat)
        messages.append((start_tick, mido.Message("note_on",  channel=ev.channel, note=ev.pitch, velocity=ev.velocity, time=0)))
        messages.append((end_tick,   mido.Message("note_off", channel=ev.channel, note=ev.pitch, velocity=0,           time=0)))

    messages.sort(key=lambda x: (x[0], 0 if x[1].type == "note_off" else 1))

    current_tick = 0
    for abs_tick, msg in messages:
        delta = abs_tick - current_tick
        track.append(msg.copy(time=delta))
        current_tick = abs_tick

    track.append(mido.MetaMessage("end_of_track", time=0))
    return track


def write_midi(
    events: List[NoteEvent],
    output_path: Path,
    bpm: int = 140,
    ticks_per_beat: int = TICKS_PER_BEAT,
) -> None:
    mid = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    tempo_track.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(tempo_track)
    mid.tracks.append(_events_to_track(events, ticks_per_beat))
    mid.save(str(output_path))


def write_combined_midi(
    parts: dict[str, List[NoteEvent]],
    output_path: Path,
    bpm: int = 140,
    ticks_per_beat: int = TICKS_PER_BEAT,
) -> None:
    mid = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    tempo_track.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(tempo_track)

    for part_name, events in parts.items():
        track = _events_to_track(events, ticks_per_beat)
        track.name = part_name
        mid.tracks.append(track)

    mid.save(str(output_path))
