#!/usr/bin/env python3
# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Mine a directory of MIDI files into a per-genre statistical prior.

Usage:
  python scripts/mine_corpus.py <midi_dir> <genre> [--out backend/app/priors]

Example (after downloading POP909 or a genre-tagged Lakh subset):
  python scripts/mine_corpus.py ~/datasets/pop909 pop

The resulting backend/app/priors/<genre>.json is picked up automatically by
app.services.priors and can bias chord-progression (and later melody) generation.

DATA USE: This tool performs local statistical mining only — it ships no music
and never copies or redistributes dataset content. YOU are responsible for
obtaining any corpus legitimately and complying with its license; the authors
accept no liability for its use, including on material you are not authorized to
use. Provided WITHOUT WARRANTY (GPL header above). See DATA_LICENSES.md.
"""
import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without installing the package
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "backend"))

from app.mining.corpus import mine_directory      # noqa: E402
from app.services.priors import describe           # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("midi_dir", help="Directory of .mid/.midi files to mine")
    ap.add_argument("genre", help="Genre label for the output prior")
    ap.add_argument("--out", default=str(_REPO / "backend/app/priors"),
                    help="Output directory for <genre>.json")
    ap.add_argument("--pattern", default=None,
                    help="rglob to restrict files, e.g. '[0-9][0-9][0-9].mid' (POP909 canonical only)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Randomly sample at most N files (for large genre folders)")
    args = ap.parse_args()

    src = Path(args.midi_dir)
    if not src.exists():
        ap.error(f"midi_dir does not exist: {src}")

    print(f"Mining {src} as genre '{args.genre}' …")
    prior = mine_directory(src, args.genre, pattern=args.pattern, limit=args.limit)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.genre}.json"
    out_path.write_text(json.dumps(prior, indent=2))

    print(f"\nWrote {out_path}\n")
    print(describe(prior))


if __name__ == "__main__":
    main()
