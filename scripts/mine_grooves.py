#!/usr/bin/env python3
# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Mine drum grooves from the Groove MIDI Dataset (or any GM drum-MIDI folder).

Groove MIDI ships an info.csv (columns: style, bpm, beat_type, time_signature,
midi_filename, …). This groups files by the genre in `style` (the part before
"/"), keeps 4/4 "beat" performances, mines each genre, and writes a groove prior
to backend/app/priors/grooves/<genre>.json.

Usage:
  python scripts/mine_grooves.py ~/datasets/groove
  python scripts/mine_grooves.py /some/drum/folder --genre funk   # no info.csv

Download: https://magenta.tensorflow.org/datasets/groove
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "backend"))

from app.mining.drums import empty_groove, analyze_drum_song, finalize_groove   # noqa: E402
from app.mining.midi_io import read_song                                        # noqa: E402


def _group_by_info_csv(root: Path) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = defaultdict(list)
    with open(root / "info.csv", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("beat_type") or "").strip() == "fill":
                continue
            ts = (row.get("time_signature") or "4-4").replace("/", "-").strip()
            if ts not in ("4-4",):
                continue
            style = (row.get("style") or "unknown").strip()
            genre = style.split("/")[0].split("-")[0] or "unknown"
            mf = (row.get("midi_filename") or "").strip()
            if mf:
                groups[genre].append(root / mf)
    return groups


def _group_flat(root: Path, genre: str) -> dict[str, list[Path]]:
    return {genre: sorted(list(root.rglob("*.mid")) + list(root.rglob("*.midi")))}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gmd_dir", help="Groove MIDI root (containing info.csv) or a drum-MIDI folder")
    ap.add_argument("--genre", default=None, help="Force a single genre (for folders without info.csv)")
    ap.add_argument("--out", default=str(_REPO / "backend/app/priors/grooves"),
                    help="Output directory")
    args = ap.parse_args()

    root = Path(args.gmd_dir)
    if not root.exists():
        ap.error(f"path does not exist: {root}")

    if args.genre:
        groups = _group_flat(root, args.genre)
    elif (root / "info.csv").exists():
        groups = _group_by_info_csv(root)
    else:
        ap.error("no info.csv found — pass --genre to mine the folder as one genre")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for genre, paths in sorted(groups.items()):
        groove = empty_groove(genre)
        used = 0
        for p in paths:
            try:
                song = read_song(p)
            except Exception:
                continue
            if analyze_drum_song(song, groove):
                used += 1
        if used == 0:
            print(f"  {genre}: no usable files, skipped")
            continue
        final = finalize_groove(groove)
        (out_dir / f"{genre}.json").write_text(json.dumps(final, indent=2))
        d = final["derived"]
        print(f"  {genre:14s} songs={final['songs']:4d}  "
              f"kick={d['kick_pattern']}  snare_beats={d['snare_standard_beats']}  "
              f"hats={d['hat_density']}  swing={d['swing']}")

    print(f"\nWrote groove priors to {out_dir}/")


if __name__ == "__main__":
    main()
