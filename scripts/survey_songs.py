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
Song survey: build full songs across styles and analyze the RESULTING MIDI
for cross-part musical problems.

The existing quality scorer (and scripts/batch_generate.py) evaluates single
loops part-by-part during generation. This tool instead runs the real song
builder end-to-end and inspects the final song.mid the way a listener would —
checking that the parts agree with EACH OTHER. It exists because two real
bugs (a verse bass frozen on the tonic while chords moved, and major-key
progression templates leaking into minor-scale styles) produced songs that
scored fine per-part but sounded wrong as a whole.

Checks per song:
  bass_out_of_chord   % of bass note-time whose pitch class is not in the
                      simultaneously sounding chord — high = bass and harmony
                      disagree (the frozen-bass bug showed up here).
  melody_clash        clash-beats per 100 beats of song where a melody note
                      sounds a semitone against a simultaneous chord/pad tone
                      — the minor-3rd-vs-major-3rd class (template case bug).
  melody_out_of_key   % of melody note-time outside BOTH the declared scale
                      and the sounding chord (chord tones are legit even when
                      chromatic, e.g. the raised 7th under a V chord).
  frozen_bass_bars    longest run of consecutive bars where the bass stays on
                      one pitch class while the chords change at least twice.
  register_overlap    % of time the chord voicing's top note reaches into the
                      melody's active register while both are sounding.
  dropout_bars        bars mid-song where drums play but no pitched part
                      sounds at all (arrangement holes).

Usage (from repo root):
    python scripts/survey_songs.py                          # 2 songs x every style
    python scripts/survey_songs.py --styles cloud_rap rnb --count 4
    python scripts/survey_songs.py --seed 1000 --template verse_chorus
    python scripts/survey_songs.py --json report.json       # machine-readable copy

Exports are kept in backend/exports/<gen_id>/ so flagged songs can be
auditioned — the report prints each song's path and seed for reproduction.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# ── path setup ────────────────────────────────────────────────────────────────
REPO_ROOT   = Path(__file__).parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import mido  # noqa: E402

from app.api.routes_song import build_song, EXPORTS_DIR  # noqa: E402
from app.models.schemas import BuildSongRequest          # noqa: E402
from app.services.style_loader import load_style, list_styles  # noqa: E402
from app.theory.scales import SCALE_INTERVALS, note_name_to_midi  # noqa: E402

PITCH_CLASS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
BEATS_PER_BAR = 4


# ── MIDI parsing ──────────────────────────────────────────────────────────────

def _parse_tracks(path: Path) -> tuple[dict[str, list], int]:
    """song.mid → {track_name: [(start_tick, pitch, velocity, dur_ticks)]}, tpb."""
    mid = mido.MidiFile(str(path))
    out: dict[str, list] = {}
    for track in mid.tracks:
        if not track.name:
            continue
        abs_time, active, notes = 0, {}, []
        for msg in track:
            abs_time += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                active[(msg.channel, msg.note)] = (abs_time, msg.velocity)
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                key = (msg.channel, msg.note)
                if key in active:
                    start, vel = active.pop(key)
                    notes.append((start, msg.note, vel, abs_time - start))
        notes.sort()
        out[track.name] = notes
    return out, mid.ticks_per_beat


def _to_beats(notes: list, tpb: int) -> list[tuple[float, int, float]]:
    """(start_tick, pitch, vel, dur_ticks) → (start_beat, pitch, dur_beats)."""
    return [(n[0] / tpb, n[1], max(n[3], 1) / tpb) for n in notes]


def _bar_of(beat: float) -> int:
    # +0.1 beat tolerance so humanize jitter just before a barline counts as
    # the next bar (a chord fired at beat 19.98 belongs to bar 5, not bar 4).
    return int((beat + 0.1) // BEATS_PER_BAR)


def _chord_pcs_by_bar(chord_notes: list[tuple[float, int, float]]) -> dict[int, set[int]]:
    by_bar: dict[int, set[int]] = defaultdict(set)
    for start, pitch, dur in chord_notes:
        first, last = _bar_of(start), _bar_of(start + dur - 0.15)
        for bar in range(first, max(first, last) + 1):
            by_bar[bar].add(pitch % 12)
    return dict(by_bar)


def _overlap(a_start: float, a_dur: float, b_start: float, b_dur: float) -> float:
    return max(0.0, min(a_start + a_dur, b_start + b_dur) - max(a_start, b_start))


# ── checks ────────────────────────────────────────────────────────────────────

def _bass_out_of_chord(bass: list, chord_bars: dict[int, set[int]]) -> float:
    """% of bass note-time whose pc is absent from the bar's chord pcs."""
    total = bad = 0.0
    for start, pitch, dur in bass:
        pcs = chord_bars.get(_bar_of(start))
        if not pcs:
            continue
        total += dur
        if pitch % 12 not in pcs:
            bad += dur
    return 100.0 * bad / total if total else 0.0


def _melody_clashes(melody: list, harmony: list, song_beats: float,
                    chord_bars: dict[int, set[int]]) -> float:
    """Semitone collisions (interval 1 or 11 mod 12) between the melody and a
    simultaneously sounding chord/pad note, as clash-beats per 100 beats of
    song — weighted by how long the two notes actually overlap.

    A melody note that is itself a chord tone is never a clash, even when
    another chord voice sits a semitone away mod 12 — the melody landing on
    the root of a maj7 chord (root vs maj-7th = 11) is normal, consonant
    writing, and counting it drowned the metric in false positives. What's
    left after this filter is the real thing: a NON-chord melody note grinding
    against a sounding chord tone (e.g. the minor-3rd-vs-major-3rd false
    relation the major/minor template bug produced)."""
    clash_beats = 0.0
    for m_start, m_pitch, m_dur in melody:
        if m_pitch % 12 in chord_bars.get(_bar_of(m_start), set()):
            continue
        for h_start, h_pitch, h_dur in harmony:
            if h_start > m_start + m_dur:
                break
            ov = _overlap(m_start, m_dur, h_start, h_dur)
            if ov <= 0.05:
                continue
            if abs(m_pitch - h_pitch) % 12 in (1, 11):
                clash_beats += ov
    return 100.0 * clash_beats / max(song_beats, 1.0)


def _melody_out_of_key(melody: list, scale_pcs: set[int], chord_bars: dict[int, set[int]]) -> float:
    total = bad = 0.0
    for start, pitch, dur in melody:
        total += dur
        pc = pitch % 12
        if pc in scale_pcs:
            continue
        if pc in chord_bars.get(_bar_of(start), set()):
            continue   # chord tone (borrowed/raised) — musically fine
        bad += dur
    return 100.0 * bad / total if total else 0.0


def _frozen_bass(bass: list, chord_bars: dict[int, set[int]]) -> int:
    """Longest run of bars where the bass holds ONE pc while chords change ≥2 times."""
    bass_bars: dict[int, set[int]] = defaultdict(set)
    for start, pitch, dur in bass:
        bass_bars[_bar_of(start)].add(pitch % 12)
    if not bass_bars:
        return 0
    worst = 0
    bars = sorted(bass_bars)
    i = 0
    while i < len(bars):
        j = i
        # extend run while consecutive bars keep the same single bass pc
        while (j + 1 < len(bars) and bars[j + 1] == bars[j] + 1
               and bass_bars[bars[j + 1]] == bass_bars[bars[i]]
               and len(bass_bars[bars[i]]) == 1):
            j += 1
        run = bars[i:j + 1]
        if len(run) >= 4:
            changes = sum(
                1 for a, b in zip(run, run[1:])
                if chord_bars.get(a) and chord_bars.get(b) and chord_bars[a] != chord_bars[b]
            )
            if changes >= 2:
                worst = max(worst, len(run))
        i = j + 1
    return worst


def _register_overlap(chords: list, melody: list) -> float:
    """% of melody note-time during which some chord note sounds AT or ABOVE it."""
    total = bad = 0.0
    for m_start, m_pitch, m_dur in melody:
        total += m_dur
        for c_start, c_pitch, c_dur in chords:
            if c_start > m_start + m_dur:
                break
            if c_pitch >= m_pitch and _overlap(m_start, m_dur, c_start, c_dur) > 0.1:
                bad += m_dur
                break
    return 100.0 * bad / total if total else 0.0


def _dropout_bars(tracks: dict[str, list]) -> int:
    """Bars where drums play but NO pitched part sounds (mid-song holes)."""
    drum_bars = {_bar_of(s) for s, _, _ in tracks.get("drums", [])}
    pitched_bars: set[int] = set()
    for name, notes in tracks.items():
        if name == "drums":
            continue
        for start, pitch, dur in notes:
            first, last = _bar_of(start), _bar_of(start + dur - 0.15)
            pitched_bars.update(range(first, max(first, last) + 1))
    return len(drum_bars - pitched_bars)


# ── survey ────────────────────────────────────────────────────────────────────

def analyze_song(song_path: Path, key: str, scale: str) -> dict:
    raw_tracks, tpb = _parse_tracks(song_path)
    tracks = {name: _to_beats(notes, tpb) for name, notes in raw_tracks.items()}

    chords = tracks.get("chords", [])
    bass   = tracks.get("bass", [])
    melody = tracks.get("melody", [])
    pads   = tracks.get("pads", [])
    harmony = sorted(chords + pads)

    chord_bars = _chord_pcs_by_bar(chords)
    root_pc = note_name_to_midi(key, 4) % 12
    scale_pcs = {(root_pc + iv) % 12 for iv in SCALE_INTERVALS.get(scale, SCALE_INTERVALS["minor"])}

    song_beats = max((s + d for t in tracks.values() for s, _, d in t), default=0.0)

    return {
        "bass_out_of_chord_pct": round(_bass_out_of_chord(bass, chord_bars), 1),
        "melody_clash_pct":  round(_melody_clashes(melody, harmony, song_beats, chord_bars), 2),
        "melody_out_of_key_pct": round(_melody_out_of_key(melody, scale_pcs, chord_bars), 1),
        "frozen_bass_bars":      _frozen_bass(bass, chord_bars),
        "register_overlap_pct":  round(_register_overlap(chords, melody), 1),
        "dropout_bars":          _dropout_bars(tracks),
    }


# Issue weights for the single "worst-first" ranking score. Roughly: harmonic
# disagreement and clashes dominate; register/dropout are secondary polish.
# Note the clash metric has a natural noise floor (~10-15%) from idiomatic
# color tones (a melody 9th rubbing the chord's 3rd, passing tones, etc.) —
# the score is for RANKING songs/styles against each other and against past
# runs, not an absolute pass/fail.
def _score(m: dict) -> float:
    return (m["bass_out_of_chord_pct"] * 1.0
            + m["melody_clash_pct"] * 3.0
            + m["melody_out_of_key_pct"] * 0.8
            + m["frozen_bass_bars"] * 2.0
            + m["register_overlap_pct"] * 0.3
            + m["dropout_bars"] * 1.5)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build songs across styles and analyze the resulting MIDI for cross-part musical problems.")
    ap.add_argument("--styles", nargs="+", default=None, help="style ids (default: all)")
    ap.add_argument("--count", type=int, default=2, help="songs per style (default 2)")
    ap.add_argument("--seed", type=int, default=100, help="base seed; song i uses seed+i")
    ap.add_argument("--template", default="verse_chorus")
    ap.add_argument("--complexity", type=float, default=0.5)
    ap.add_argument("--variation", type=float, default=0.5)
    ap.add_argument("--json", metavar="PATH", default=None, help="also write the full report as JSON")
    args = ap.parse_args()

    style_ids = args.styles or [s["id"] for s in list_styles()]
    results: list[dict] = []

    for style_id in style_ids:
        try:
            style = load_style(style_id)
        except ValueError:
            print(f"!! unknown style {style_id!r} — skipped", file=sys.stderr)
            continue
        scale = style.get("default_scale", "minor")
        key = (style.get("preferred_keys") or ["C"])[0]
        bpm_lo, bpm_hi = style.get("bpm_range", [90, 120])

        for i in range(args.count):
            seed = args.seed + i
            req = BuildSongRequest(
                style_id=style_id, key=key, scale=scale, bpm=(bpm_lo + bpm_hi) // 2,
                complexity=args.complexity, variation=args.variation,
                parts=["chords", "bass", "melody", "drums", "pads"],
                template=args.template, seed=seed,
            )
            try:
                resp = build_song(req)
            except Exception as exc:  # a style that can't build a song at all is itself a finding
                print(f"!! {style_id} seed={seed}: build failed: {exc}", file=sys.stderr)
                results.append({"style": style_id, "seed": seed, "error": str(exc)})
                continue
            song_path = EXPORTS_DIR / resp.generation_id / "song.mid"
            metrics = analyze_song(song_path, key, scale)
            results.append({
                "style": style_id, "seed": seed, "key": f"{key} {scale}",
                "generation_id": resp.generation_id, "path": str(song_path),
                **metrics, "issue_score": round(_score(metrics), 1),
            })
            print(f"  built {style_id} seed={seed} -> {resp.generation_id} (score {results[-1]['issue_score']})")

    ok = [r for r in results if "error" not in r]
    ok.sort(key=lambda r: -r["issue_score"])

    print("\n" + "=" * 100)
    print(f"{'style':<18}{'seed':>6}  {'bassX%':>7}{'clash%':>9}{'offkey%':>9}{'frozen':>8}{'regovr%':>9}{'dropout':>9}{'SCORE':>8}  gen_id")
    print("-" * 100)
    for r in ok:
        print(f"{r['style']:<18}{r['seed']:>6}  {r['bass_out_of_chord_pct']:>7}{r['melody_clash_pct']:>9}"
              f"{r['melody_out_of_key_pct']:>9}{r['frozen_bass_bars']:>8}{r['register_overlap_pct']:>9}"
              f"{r['dropout_bars']:>9}{r['issue_score']:>8}  {r['generation_id']}")

    if ok:
        print("-" * 100)
        by_style: dict[str, list[float]] = defaultdict(list)
        for r in ok:
            by_style[r["style"]].append(r["issue_score"])
        print("style averages (worst first):")
        for style_id, scores in sorted(by_style.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
            print(f"  {style_id:<18} avg score {sum(scores) / len(scores):>6.1f}   ({len(scores)} songs)")
        worst = ok[0]
        print(f"\nworst song: {worst['style']} seed={worst['seed']} -> {worst['path']}")
        print("(exports are kept — audition any flagged song and re-run its exact seed to reproduce)")

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2))
        print(f"\nJSON report written to {args.json}")


if __name__ == "__main__":
    main()
