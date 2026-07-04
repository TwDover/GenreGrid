#!/usr/bin/env python3
# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Bucket the Lakh MIDI Dataset (LMD-matched) into per-genre folders using the
tagtraum MSD genre annotations, ready for mine_corpus.py.

LMD-matched paths embed the MSD track id as the leaf directory
(lmd_matched/L/L/L/TRLLLJH.../<md5>.mid), and the tagtraum .cls maps
"trackid<TAB>genre". We join them and symlink one MIDI per track into
<out>/<genre>/, so nothing is copied and the 1.4 GB stays in one place.

Usage:
  python scripts/filter_lakh_genres.py \
      --lmd ~/Downloads/lmd_matched \
      --cls ~/Downloads/tagtraum_cls/msd_tagtraum_cd2.cls \
      --out ~/Downloads/lakh_by_genre

────────────────────────────────────────────────────────────────────────────
DATA USE & LICENSING NOTICE
────────────────────────────────────────────────────────────────────────────
This script is a *tool*. It ships no music. It reads MIDI files and genre
labels that already exist on YOUR machine and only creates symbolic links to
them — it never copies, embeds, redistributes, or uploads any dataset content,
and no MIDI or dataset file is ever committed to this repository.

The Lakh MIDI Dataset, the tagtraum genre annotations, and any other corpus you
point this at are governed by THEIR OWN licenses and by the copyright of the
underlying musical works, which may be owned by third parties. GenreGrid does
not grant you any rights to that material and is not affiliated with those
datasets or their rights-holders.

YOU are solely responsible for:
  • obtaining each dataset legitimately and complying with its license/terms;
  • ensuring you have the right to analyze the material in your jurisdiction;
  • not redistributing the source files or anything that reproduces them.

This tool is provided WITHOUT ANY WARRANTY (see the GPL header above). The
GenreGrid authors accept NO liability for how it is used, including any use to
process material you are not authorized to use. Intended use is local,
statistical mining (aggregate patterns — chord n-grams, rhythm histograms),
not the reproduction or distribution of any copyrighted work.
"""
import argparse
from collections import Counter
from pathlib import Path


def load_genres(cls_path: Path) -> dict[str, str]:
    """trackid -> primary genre (lowercased, spaces stripped)."""
    genres: dict[str, str] = {}
    with open(cls_path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2 or not parts[1]:
                continue
            genres[parts[0]] = parts[1].strip().lower().replace(" ", "")
    return genres


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lmd", required=True, help="Extracted lmd_matched directory")
    ap.add_argument("--cls", required=True, help="tagtraum .cls genre file")
    ap.add_argument("--out", required=True, help="Output directory for per-genre folders")
    ap.add_argument("--per-track", type=int, default=1, help="Max MIDIs to link per track (default 1)")
    args = ap.parse_args()

    lmd = Path(args.lmd).expanduser()
    out = Path(args.out).expanduser()
    genres = load_genres(Path(args.cls).expanduser())
    print(f"Loaded {len(genres)} genre labels.")

    counts: Counter = Counter()
    linked = 0
    # Track dirs are named TR... anywhere under lmd_matched.
    for track_dir in lmd.rglob("TR*"):
        if not track_dir.is_dir():
            continue
        genre = genres.get(track_dir.name)
        if not genre:
            continue
        mids = sorted(track_dir.glob("*.mid"))[: args.per_track]
        if not mids:
            continue
        gdir = out / genre
        gdir.mkdir(parents=True, exist_ok=True)
        for i, mid in enumerate(mids):
            link = gdir / f"{track_dir.name}_{i}.mid"
            if link.exists() or link.is_symlink():
                continue
            link.symlink_to(mid.resolve())
            counts[genre] += 1
            linked += 1

    print(f"\nLinked {linked} MIDIs into {out}/\n")
    for genre, n in counts.most_common():
        print(f"  {genre:14s} {n}")


if __name__ == "__main__":
    main()
