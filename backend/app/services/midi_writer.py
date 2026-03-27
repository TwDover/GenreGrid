"""Translate NoteEvent lists into .mid files using mido."""
from collections import defaultdict
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


def _trim_overlaps(events: List[NoteEvent]) -> List[NoteEvent]:
    """Trim note durations so same pitch+channel notes never overlap.

    A second note_on for the same pitch without a note_off in between causes
    stuck notes in most DAWs. Shorten the earlier note to end just before the
    next one starts.
    """
    by_lane: dict[tuple, list] = defaultdict(list)
    for ev in events:
        by_lane[(ev.channel, ev.pitch)].append(ev)

    result = []
    for evts in by_lane.values():
        evts.sort(key=lambda e: e.start)
        for i, ev in enumerate(evts):
            if i + 1 < len(evts):
                gap = evts[i + 1].start - ev.start
                dur = min(ev.duration, max(0.02, gap - 0.02))
            else:
                dur = ev.duration
            result.append(NoteEvent(ev.pitch, ev.start, dur, ev.velocity, ev.channel))
    return result


def _events_to_track(events: List[NoteEvent], ticks_per_beat: int = TICKS_PER_BEAT) -> mido.MidiTrack:
    track = mido.MidiTrack()
    messages = []

    events = _trim_overlaps(events)

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
    program: int | None = None,
) -> None:
    mid = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    tempo_track.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(tempo_track)
    track = _events_to_track(events, ticks_per_beat)
    if program is not None and events:
        track.insert(0, mido.Message("program_change", channel=events[0].channel, program=program, time=0))
    mid.tracks.append(track)
    mid.save(str(output_path))


def rebuild_combined_from_parts(output_dir: Path, bpm: int, ticks_per_beat: int = TICKS_PER_BEAT) -> None:
    """Rebuild combined.mid by merging all per-part .mid files present in output_dir.

    Called after regenerating a single part so combined.mid stays in sync without
    needing to re-generate events for every part from scratch.
    """
    part_files = sorted(f for f in output_dir.glob("*.mid") if f.name != "combined.mid")
    if not part_files:
        return

    combined = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    tempo_track.append(mido.MetaMessage("end_of_track", time=0))
    combined.tracks.append(tempo_track)

    for part_file in part_files:
        part_mid = mido.MidiFile(str(part_file))
        for track in part_mid.tracks:
            # Skip pure-meta tracks (tempo tracks); copy note-bearing tracks only
            if any(msg.type not in ("set_tempo", "end_of_track", "time_signature", "key_signature") for msg in track):
                track.name = part_file.stem
                combined.tracks.append(track)

    combined.save(str(output_dir / "combined.mid"))


def write_combined_midi(
    parts: dict[str, List[NoteEvent]],
    output_path: Path,
    bpm: int = 140,
    ticks_per_beat: int = TICKS_PER_BEAT,
    programs: dict[str, int] | None = None,
) -> None:
    mid = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    tempo_track.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(tempo_track)

    for part_name, events in parts.items():
        track = _events_to_track(events, ticks_per_beat)
        if programs and part_name in programs and events:
            track.insert(0, mido.Message("program_change", channel=events[0].channel, program=programs[part_name], time=0))
        track.name = part_name
        mid.tracks.append(track)

    mid.save(str(output_path))
