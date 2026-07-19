#!/usr/bin/env python3
# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""
Hook-score calibration (roadmap-2 item 3).

Before wiring the chorus hook score into a hard gate, we need to know its
distribution — where our generator's choruses land today, and (if a corpus of
human choruses is available) where real hooks land. This prints both so a
sensible threshold can be chosen without guessing.

  python scripts/calibrate_hooks.py                       # generator, all styles x 12 seeds
  python scripts/calibrate_hooks.py --styles pop rnb funk --count 20
  python scripts/calibrate_hooks.py --pop909 ~/datasets/pop909   # + human reference

The generator pass builds real songs (verse_chorus template) and scores every
chorus melody with services.quality._hook_score — the exact function the search
optimises. The optional --pop909 pass scores the melody track of each POP909
song (channel/track heuristics; whole melody, since we lack chorus labels) to
give a human baseline distribution to aim at.
"""

import argparse
import statistics
import sys
from pathlib import Path

REPO_ROOT   = Path(__file__).parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import mido  # noqa: E402

from app.api.routes_song import build_song, EXPORTS_DIR         # noqa: E402
from app.models.schemas import BuildSongRequest                 # noqa: E402
from app.services.style_loader import load_style, list_styles   # noqa: E402
from app.services.quality import _hook_score                    # noqa: E402
from app.services.midi_writer import NoteEvent                  # noqa: E402

# survey_songs already parses song.mid into per-part beat notes and loads the
# section structure — reuse it rather than reimplement the MIDI plumbing.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from survey_songs import _parse_tracks, _to_beats, _load_sections  # noqa: E402


def _dist(label: str, scores: list[float]) -> None:
    if not scores:
        print(f"  {label:<22} (no scores)")
        return
    scores = sorted(scores)
    med = statistics.median(scores)
    lo, hi = scores[0], scores[-1]
    p25 = scores[len(scores) // 4]
    p75 = scores[(len(scores) * 3) // 4]
    print(f"  {label:<22} n={len(scores):<4} median={med:.3f}  "
          f"IQR[{p25:.3f}–{p75:.3f}]  range[{lo:.3f}–{hi:.3f}]")


def _chorus_hook_scores(song_path: Path) -> list[float]:
    raw, tpb = _parse_tracks(song_path)
    melody = _to_beats(raw.get("melody", []), tpb)
    out: list[float] = []
    for sec in _load_sections(song_path):
        if sec.get("section_type") != "chorus":
            continue
        lo = sec.get("start_bar", 0) * 4.0
        hi = lo + sec.get("bars", 0) * 4.0
        mel = [NoteEvent(p, s, d, 90, 2) for s, p, d in melody if lo <= s < hi]
        s, _ = _hook_score(mel)
        if s is not None:
            out.append(s)
    return out


def _pop909_melody_notes(path: Path) -> list[NoteEvent]:
    """POP909 files carry three tracks — MELODY, BRIDGE, PIANO. Score the
    melody track (named 'MELODY' by the dataset; fall back to the highest-pitched
    track). Whole-song melody: we have no chorus labels here."""
    mid = mido.MidiFile(str(path))
    tpb = mid.ticks_per_beat
    best_notes: list[NoteEvent] = []
    best_avg = -1.0
    for track in mid.tracks:
        name = ""
        abs_t, active, notes = 0, {}, []
        for msg in track:
            abs_t += msg.time
            if msg.type == "track_name":
                name = (msg.name or "").upper()
            elif msg.type == "note_on" and msg.velocity > 0:
                active[msg.note] = abs_t
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                if msg.note in active:
                    st = active.pop(msg.note)
                    notes.append(NoteEvent(msg.note, st / tpb, max(abs_t - st, 1) / tpb, 90, 2))
        if not notes:
            continue
        if "MELODY" in name:
            return notes
        avg = sum(n.pitch for n in notes) / len(notes)
        if avg > best_avg:
            best_avg, best_notes = avg, notes
    return best_notes


def main() -> None:
    ap = argparse.ArgumentParser(description="Calibrate the chorus hook score distribution.")
    ap.add_argument("--styles", nargs="+", default=None, help="style ids (default: all)")
    ap.add_argument("--count", type=int, default=12, help="songs per style (default 12)")
    ap.add_argument("--seed", type=int, default=500, help="base seed; song i uses seed+i")
    ap.add_argument("--template", default="verse_chorus")
    ap.add_argument("--pop909", metavar="DIR", default=None,
                    help="a POP909 (or any melody-MIDI) directory to score as a human reference")
    args = ap.parse_args()

    style_ids = args.styles or [s["id"] for s in list_styles()]
    all_gen: list[float] = []

    print("== generator chorus hook scores ==")
    for style_id in style_ids:
        try:
            style = load_style(style_id)
        except ValueError:
            print(f"!! unknown style {style_id!r} — skipped", file=sys.stderr)
            continue
        scale = style.get("default_scale", "minor")
        key = (style.get("preferred_keys") or ["C"])[0]
        bpm_lo, bpm_hi = style.get("bpm_range", [90, 120])
        per_style: list[float] = []
        for i in range(args.count):
            req = BuildSongRequest(
                style_id=style_id, key=key, scale=scale, bpm=(bpm_lo + bpm_hi) // 2,
                complexity=0.6, variation=0.5,
                parts=["chords", "bass", "melody", "drums", "pads"],
                template=args.template, seed=args.seed + i,
            )
            try:
                resp = build_song(req)
            except Exception as exc:
                print(f"!! {style_id} seed={args.seed + i}: build failed: {exc}", file=sys.stderr)
                continue
            per_style += _chorus_hook_scores(EXPORTS_DIR / resp.generation_id / "song.mid")
        _dist(style_id, per_style)
        all_gen += per_style

    print("-" * 78)
    _dist("ALL GENERATOR", all_gen)

    if args.pop909:
        print("\n== human reference (POP909 melody tracks) ==")
        ref: list[float] = []
        for mid_path in sorted(Path(args.pop909).rglob("*.mid")):
            s, _ = _hook_score(_pop909_melody_notes(mid_path))
            if s is not None:
                ref.append(s)
        _dist("POP909 melodies", ref)
        if ref and all_gen:
            print(f"\n  gap (human median − generator median): "
                  f"{statistics.median(ref) - statistics.median(all_gen):+.3f}")


if __name__ == "__main__":
    main()
