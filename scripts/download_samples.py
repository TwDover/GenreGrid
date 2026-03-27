#!/usr/bin/env python3
"""
Download free instrument samples into frontend/public/samples/.

Sources:
  Drums   — https://tonejs.github.io/audio/drum-samples/{Kit}/{file}.mp3
  Bass    — https://gleitz.github.io/midi-js-soundfonts/MusyngKite/{inst}-mp3/{note}.mp3
  Melodic — same gleitz base

Run from repo root:
  python scripts/download_samples.py
"""

import os
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent / "frontend" / "public" / "samples"

# ---------------------------------------------------------------------------
# Drum kits
# ---------------------------------------------------------------------------
DRUM_BASE = "https://tonejs.github.io/audio/drum-samples"
DRUM_KITS = ["acoustic-kit", "CR78", "KPR77", "LINN", "R8", "Techno", "breakbeat8", "breakbeat13"]
DRUM_FILES = ["kick", "snare", "hihat", "tom1", "tom2", "tom3"]

# ---------------------------------------------------------------------------
# Bass instruments  (7 sparse notes — Sampler interpolates the rest)
# ---------------------------------------------------------------------------
GLEITZ_BASE = "https://gleitz.github.io/midi-js-soundfonts/MusyngKite"
BASS_NOTES = ["A1", "C2", "E2", "A2", "C3", "E3", "A3"]
BASS_INSTRUMENTS = [
    "electric_bass_finger",
    "slap_bass_1",
    "fretless_bass",
    "acoustic_bass",
    "synth_bass_1",
    "electric_bass_pick",
]

# ---------------------------------------------------------------------------
# Melodic instruments  (10 sparse notes)
# ---------------------------------------------------------------------------
MELODIC_NOTES = ["A2", "C3", "E3", "A3", "C4", "E4", "A4", "C5", "E5", "A5"]
MELODIC_INSTRUMENTS = [
    "electric_piano_1",
    "electric_piano_2",
    "drawbar_organ",
    "vibraphone",
    "acoustic_guitar_nylon",
    "clavinet",
    "accordion",
    "string_ensemble_1",
]


def note_to_gleitz_filename(note: str) -> str:
    """Convert e.g. 'A#3' → 'As3' (gleitz uses 's' for sharps)."""
    return note.replace("#", "s")


def download(url: str, dest: Path) -> None:
    if dest.exists():
        print(f"  skip  {dest.name}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(url, dest)
        print(f"  ok    {dest.relative_to(BASE_DIR.parent.parent.parent)}")
    except Exception as e:
        print(f"  FAIL  {url}  → {e}", file=sys.stderr)


def main() -> None:
    print("=== Drum kits ===")
    for kit in DRUM_KITS:
        for file in DRUM_FILES:
            url = f"{DRUM_BASE}/{kit}/{file}.mp3"
            dest = BASE_DIR / "drums" / kit / f"{file}.mp3"
            download(url, dest)

    print("\n=== Bass instruments ===")
    for inst in BASS_INSTRUMENTS:
        for note in BASS_NOTES:
            fname = note_to_gleitz_filename(note)
            url = f"{GLEITZ_BASE}/{inst}-mp3/{fname}.mp3"
            dest = BASE_DIR / "bass" / inst / f"{fname}.mp3"
            download(url, dest)

    print("\n=== Melodic instruments ===")
    for inst in MELODIC_INSTRUMENTS:
        for note in MELODIC_NOTES:
            fname = note_to_gleitz_filename(note)
            url = f"{GLEITZ_BASE}/{inst}-mp3/{fname}.mp3"
            dest = BASE_DIR / "melodic" / inst / f"{fname}.mp3"
            download(url, dest)

    print("\nDone.")


if __name__ == "__main__":
    main()
