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

import shutil
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent / "frontend" / "public" / "samples"

# ---------------------------------------------------------------------------
# Drum kits
# ---------------------------------------------------------------------------
DRUM_BASE = "https://tonejs.github.io/audio/drum-samples"
DRUM_KITS = ["acoustic-kit", "CR78", "KPR77", "LINN", "R8", "Techno", "breakbeat8", "breakbeat13"]

# Core files available in every kit
DRUM_CORE = ["kick", "snare", "hihat", "tom1", "tom2", "tom3"]
# Extra articulation files — attempted per kit; falls back to hihat copy if absent on CDN
DRUM_EXTRAS = ["hihat_open", "crash", "ride"]

# ---------------------------------------------------------------------------
# Bass instruments  (denser notes — Sampler interpolates shorter distances)
# ---------------------------------------------------------------------------
GLEITZ_BASE = "https://gleitz.github.io/midi-js-soundfonts/MusyngKite"
BASS_NOTES = ["A1", "C2", "E2", "G2", "A2", "C3", "E3", "G3", "A3"]
BASS_INSTRUMENTS = [
    "electric_bass_finger",
    "slap_bass_1",
    "fretless_bass",
    "acoustic_bass",
    "synth_bass_1",
    "electric_bass_pick",
]

# ---------------------------------------------------------------------------
# Melodic instruments  (denser notes — reduces pitch-stretch artefacts)
# ---------------------------------------------------------------------------
MELODIC_NOTES = ["A2", "C3", "E3", "G3", "A3", "C4", "E4", "G4", "A4", "C5", "E5", "G5", "A5"]
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


def download(url: str, dest: Path) -> bool:
    """Return True if downloaded, False if skipped or failed."""
    if dest.exists():
        print(f"  skip  {dest.name}")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(url, dest)
        print(f"  ok    {dest.relative_to(BASE_DIR.parent.parent.parent)}")
        return True
    except Exception as e:
        print(f"  FAIL  {url}  → {e}", file=sys.stderr)
        return False


def main() -> None:
    print("=== Drum kits ===")
    for kit in DRUM_KITS:
        kit_dir = BASE_DIR / "drums" / kit
        print(f"\n  kit: {kit}")

        # Core samples
        for file in DRUM_CORE:
            url = f"{DRUM_BASE}/{kit}/{file}.mp3"
            download(url, kit_dir / f"{file}.mp3")

        # Extra articulations: try CDN first, copy hihat as fallback
        hihat_src = kit_dir / "hihat.mp3"
        for extra in DRUM_EXTRAS:
            dest = kit_dir / f"{extra}.mp3"
            if dest.exists():
                print(f"  skip  {dest.name}")
                continue
            url = f"{DRUM_BASE}/{kit}/{extra}.mp3"
            try:
                urllib.request.urlretrieve(url, dest)
                print(f"  ok    {dest.relative_to(BASE_DIR.parent.parent.parent)}")
            except Exception:
                # CDN doesn't have this articulation — copy hihat as placeholder
                if hihat_src.exists():
                    shutil.copy(hihat_src, dest)
                    print(f"  copy  {dest.name} (hihat placeholder — replace with real sample)")
                else:
                    print(f"  skip  {dest.name} (no hihat to copy from yet)", file=sys.stderr)

    print("\n=== Bass instruments ===")
    for inst in BASS_INSTRUMENTS:
        print(f"\n  {inst}")
        for note in BASS_NOTES:
            fname = note_to_gleitz_filename(note)
            url = f"{GLEITZ_BASE}/{inst}-mp3/{fname}.mp3"
            dest = BASE_DIR / "bass" / inst / f"{note}.mp3"
            download(url, dest)

    print("\n=== Melodic instruments ===")
    for inst in MELODIC_INSTRUMENTS:
        print(f"\n  {inst}")
        for note in MELODIC_NOTES:
            fname = note_to_gleitz_filename(note)
            url = f"{GLEITZ_BASE}/{inst}-mp3/{fname}.mp3"
            dest = BASE_DIR / "melodic" / inst / f"{note}.mp3"
            download(url, dest)

    print("\nDone.")
    print("\nTip: for best drum quality, replace the hihat_open/crash/ride placeholders")
    print("in frontend/public/samples/drums/ with real one-shots (freesound.org CC0).")


if __name__ == "__main__":
    main()
