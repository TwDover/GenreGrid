# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
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


def read_note_starts(path) -> list[tuple[float, int]]:
    """Read a .mid file and return (start_beat, pitch) for every note-on.

    Lightweight — used when another part needs the harmony of an already-saved
    part (e.g. regenerating the arpeggio against the existing chords.mid).
    """
    mid = mido.MidiFile(str(path))
    tpb = mid.ticks_per_beat or TICKS_PER_BEAT
    notes: list[tuple[float, int]] = []
    for track in mid.tracks:
        abs_t = 0
        for msg in track:
            abs_t += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                notes.append((abs_t / tpb, msg.note))
    return notes


@dataclass
class ControlEvent:
    control: int    # CC number (e.g. 10=pan, 11=expression, 64=sustain)
    value: int      # 0-127
    start: float    # in beats
    channel: int = 0


@dataclass
class PitchBendEvent:
    value: int      # -8192 to 8191  (0 = no bend)
    start: float    # in beats
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


def _events_to_track(
    events: List[NoteEvent],
    ticks_per_beat: int = TICKS_PER_BEAT,
    cc_events: "List[ControlEvent] | None" = None,
    pb_events: "List[PitchBendEvent] | None" = None,
) -> mido.MidiTrack:
    track = mido.MidiTrack()
    messages = []

    events = _trim_overlaps(events)

    # Clamp ticks to >= 0. Swing/jitter can nudge a downbeat event a hair before
    # t=0, and mido rejects negative delta times — so a stray -0.006 beat kick
    # would otherwise crash the whole write.
    for ev in events:
        start_tick = max(0, int(ev.start * ticks_per_beat))
        end_tick = max(start_tick, int((ev.start + ev.duration) * ticks_per_beat))
        messages.append((start_tick, mido.Message("note_on",  channel=ev.channel, note=ev.pitch, velocity=ev.velocity, time=0)))
        messages.append((end_tick,   mido.Message("note_off", channel=ev.channel, note=ev.pitch, velocity=0,           time=0)))

    if cc_events:
        for cc in cc_events:
            tick = max(0, int(cc.start * ticks_per_beat))
            messages.append((tick, mido.Message("control_change", channel=cc.channel, control=cc.control, value=cc.value, time=0)))

    if pb_events:
        for pb in pb_events:
            tick = max(0, int(pb.start * ticks_per_beat))
            messages.append((tick, mido.Message("pitchwheel", channel=pb.channel, pitch=pb.value, time=0)))

    def _sort_key(item):
        tick, msg = item
        order = {"note_off": 0, "control_change": 1, "pitchwheel": 1, "note_on": 2}.get(msg.type, 3)
        return (tick, order)
    messages.sort(key=_sort_key)

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
    cc_events: "List[ControlEvent] | None" = None,
    pb_events: "List[PitchBendEvent] | None" = None,
) -> None:
    mid = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, clocks_per_click=24, notated_32nd_notes_per_beat=8, time=0))
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    tempo_track.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(tempo_track)
    track = _events_to_track(events, ticks_per_beat, cc_events, pb_events)
    if program is not None and events:
        track.insert(0, mido.Message("program_change", channel=events[0].channel, program=program, time=0))
    mid.tracks.append(track)
    mid.save(str(output_path))


def concatenate_midi_files(paths: list[Path], out_ticks: int = TICKS_PER_BEAT) -> mido.MidiFile:
    """Sequentially concatenate MIDI files into a single arrangement.

    Each file starts immediately after the previous one ends. Tracks from
    different files are kept separate, which DAWs handle well in type-1 MIDI.
    """
    out = mido.MidiFile(type=1, ticks_per_beat=out_ticks)
    tempo = mido.bpm2tempo(120)

    if paths:
        first = mido.MidiFile(str(paths[0]))
        for track in first.tracks:
            for msg in track:
                if msg.type == "set_tempo":
                    tempo = msg.tempo
                    break
            else:
                continue
            break

    t_track = mido.MidiTrack()
    t_track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4,
                                    clocks_per_click=24, notated_32nd_notes_per_beat=8, time=0))
    t_track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    t_track.append(mido.MetaMessage("end_of_track", time=0))
    out.tracks.append(t_track)

    offset_ticks = 0
    for path in paths:
        mid = mido.MidiFile(str(path))
        scale = out_ticks / mid.ticks_per_beat

        max_abs = 0
        for track in mid.tracks:
            abs_t = 0
            for msg in track:
                abs_t += msg.time
            max_abs = max(max_abs, abs_t)
        file_dur = int(max_abs * scale)

        for track in mid.tracks:
            has_notes = any(
                msg.type not in ("set_tempo", "end_of_track", "time_signature",
                                 "key_signature", "track_name", "instrument_name")
                for msg in track
            )
            if not has_notes:
                continue

            abs_msgs: list[tuple[int, object]] = []
            abs_t = 0
            for msg in track:
                abs_t += msg.time
                if msg.type == "end_of_track":
                    continue
                abs_msgs.append((offset_ticks + int(abs_t * scale), msg))

            abs_msgs.sort(key=lambda x: x[0])
            new_track = mido.MidiTrack()
            prev = 0
            for t, msg in abs_msgs:
                new_track.append(msg.copy(time=t - prev))
                prev = t
            new_track.append(mido.MetaMessage("end_of_track", time=0))
            out.tracks.append(new_track)

        offset_ticks += file_dur

    return out


def rebuild_combined_from_parts(output_dir: Path, bpm: int, ticks_per_beat: int = TICKS_PER_BEAT,
                                combined_name: str = "combined.mid") -> None:
    """Rebuild the combined .mid by merging all per-part .mid files in output_dir.

    Called after regenerating a single part so the combined stays in sync without
    re-generating events for every part. `combined_name` is "combined.mid" for
    loop/arrangement generations and "song.mid" for full songs.
    """
    part_files = sorted(f for f in output_dir.glob("*.mid") if f.name != combined_name)
    if not part_files:
        return

    combined = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, clocks_per_click=24, notated_32nd_notes_per_beat=8, time=0))
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

    combined.save(str(output_dir / combined_name))


def write_combined_midi(
    parts: dict[str, List[NoteEvent]],
    output_path: Path,
    bpm: int = 140,
    ticks_per_beat: int = TICKS_PER_BEAT,
    programs: dict[str, int] | None = None,
    cc_parts: "dict[str, List[ControlEvent]] | None" = None,
    pb_parts: "dict[str, List[PitchBendEvent]] | None" = None,
) -> None:
    mid = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, clocks_per_click=24, notated_32nd_notes_per_beat=8, time=0))
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    tempo_track.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(tempo_track)

    for part_name, events in parts.items():
        track = _events_to_track(
            events, ticks_per_beat,
            cc_parts.get(part_name) if cc_parts else None,
            pb_parts.get(part_name) if pb_parts else None,
        )
        if programs and part_name in programs and events:
            track.insert(0, mido.Message("program_change", channel=events[0].channel, program=programs[part_name], time=0))
        track.name = part_name
        mid.tracks.append(track)

    mid.save(str(output_path))
