# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Mine a directory of MIDI files into a per-genre statistical prior."""
from collections import Counter, defaultdict
from pathlib import Path

from app.mining.analysis import bar_chords, detect_key, in_scale_degree
from app.mining.midi_io import MidiSong, Note, read_song
from app.theory.notes import note_name_to_midi

_DRUM_CHANNEL = 9


def _avg_polyphony(notes: list[Note]) -> float:
    """Mean simultaneous voices ≈ total note-length / time span. ~1 ⇒ monophonic."""
    if not notes:
        return 0.0
    span = max(n.start + n.duration for n in notes) - min(n.start for n in notes)
    if span <= 0:
        return float(len(notes))
    return sum(n.duration for n in notes) / span


def find_melody_channel(song: MidiSong) -> int | None:
    """Pick the most melody-like pitched channel: high register, low polyphony."""
    best_ch, best_score = None, -1e9
    for ch, notes in song.by_channel().items():
        if ch == _DRUM_CHANNEL or len(notes) < 4:
            continue
        mean_pitch = sum(n.pitch for n in notes) / len(notes)
        poly = _avg_polyphony(notes)
        # Favour high register; penalise chordal (polyphonic) channels heavily.
        score = mean_pitch - 30.0 * max(0.0, poly - 1.2)
        if score > best_score:
            best_score, best_ch = score, ch
    return best_ch


def _monophonic_line(notes: list[Note]) -> list[Note]:
    """Reduce to a single line: at each onset keep only the highest note."""
    by_start: dict[float, Note] = {}
    for n in sorted(notes, key=lambda x: (x.start, -x.pitch)):
        key = round(n.start, 3)
        if key not in by_start:
            by_start[key] = n
    return [by_start[k] for k in sorted(by_start)]


def _empty_harmony() -> dict:
    return {"unigram": {}, "bigram": {}, "starts": {}, "loops4": {}}


def _empty_prior(genre: str) -> dict:
    return {
        "genre": genre,
        "songs": 0,
        "keys": {"major": 0, "minor": 0},
        # Pooled across all songs (used for describe/summary).
        "harmony": _empty_harmony(),
        # Split by mode so a major-key request samples major progressions.
        "harmony_by_mode": {"major": _empty_harmony(), "minor": _empty_harmony()},
        "melody": {
            "intervals": {}, "interval_bigrams": {}, "durations": {},
            "scale_degrees": {}, "rest_events": 0, "note_events": 0,
        },
    }


def _add(counter: dict, key, n: int = 1) -> None:
    counter[key] = counter.get(key, 0) + n


def analyze_song(song: MidiSong, prior: dict) -> bool:
    """Fold one song's statistics into `prior`. Returns False if unusable."""
    pitched = song.pitched_notes()
    if len(pitched) < 8:
        return False

    key_name, mode = detect_key(song)
    tonic_pc = note_name_to_midi(key_name, 4) % 12
    prior["keys"][mode] = prior["keys"].get(mode, 0) + 1

    # ── Harmony: per-bar roman tokens → unigram / bigram / start / 4-loop ──────
    tokens = bar_chords(song, tonic_pc, pitched, mode)
    # Collapse immediate repeats so "hold a chord for 2 bars" isn't over-counted.
    collapsed = [t for i, t in enumerate(tokens) if i == 0 or t != tokens[i - 1]]
    mode_key = "major" if mode == "major" else "minor"
    for h in (prior["harmony"], prior["harmony_by_mode"][mode_key]):
        if collapsed:
            _add(h["starts"], collapsed[0])
        for t in collapsed:
            _add(h["unigram"], t)
        for a, b in zip(collapsed, collapsed[1:]):
            h["bigram"].setdefault(a, {})
            _add(h["bigram"][a], b)
        if len(collapsed) >= 4:
            _add(h["loops4"], ",".join(collapsed[:4]))

    # ── Melody: interval / phrase-bigram / rhythm / scale-degree stats ─────────
    mel_ch = find_melody_channel(song)
    if mel_ch is not None:
        line = _monophonic_line(song.by_channel()[mel_ch])
        m = prior["melody"]
        prev_interval = None
        for i, note in enumerate(line):
            step = min(1.0, max(0.0, note.duration))
            dur_steps = max(1, min(16, round(note.duration / 0.25)))
            _add(m["durations"], dur_steps)
            deg = in_scale_degree(note.pitch, tonic_pc, mode)
            _add(m["scale_degrees"], deg if deg is not None else -1)
            m["note_events"] += 1
            if i > 0:
                gap = note.start - (line[i - 1].start + line[i - 1].duration)
                if gap > 0.25:
                    m["rest_events"] += 1
                interval = max(-12, min(12, note.pitch - line[i - 1].pitch))
                _add(m["intervals"], interval)
                if prev_interval is not None:
                    _add(m["interval_bigrams"], f"{prev_interval},{interval}")
                prev_interval = interval
            _ = step

    prior["songs"] += 1
    return True


def mine_directory(directory: str | Path, genre: str, pattern: str | None = None) -> dict:
    """Walk `directory` for MIDI files and return an aggregated prior.

    `pattern` restricts which files are mined (rglob glob). Default mines every
    .mid/.midi; pass e.g. "[0-9][0-9][0-9].mid" to take only canonical files and
    skip alternate-version re-voicings of the same songs.
    """
    prior = _empty_prior(genre)
    root = Path(directory)
    if pattern:
        files = sorted(root.rglob(pattern))
    else:
        files = sorted(list(root.rglob("*.mid")) + list(root.rglob("*.midi")))
    used = 0
    for path in files:
        try:
            song = read_song(path)
        except Exception:
            continue
        if analyze_song(song, prior):
            used += 1
    prior["files_seen"] = len(files)
    prior["files_used"] = used
    return prior


# JSON keys for the durations/intervals/scale_degrees dicts are ints; JSON turns
# them into strings on round-trip. These helpers normalise back to a clean model.
def normalize_int_keys(counter: dict) -> dict:
    return {int(k): v for k, v in counter.items()}
