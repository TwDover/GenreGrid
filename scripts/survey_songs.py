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
  melody_clash        weighted clash-beats per 100 beats of song where a
                      non-chord melody note sits an ACTUAL m2 or m9 from a
                      simultaneous chord/pad tone (wider mod-12 relatives like
                      maj7/add9 color are consonant and not counted).
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

# MIDI channel → part role. Channels are the stable contract (see mixdown's
# _PART_CHANNELS + GM channel 10 for drums); track NAMES are display labels
# (instrument names like "Alto Sax") and must not be used for identification.
_CHANNEL_PARTS = {0: "chords", 1: "bass", 2: "melody", 3: "arpeggio",
                  4: "pads", 5: "counter_melody", 9: "drums"}


def _parse_tracks(path: Path) -> tuple[dict[str, list], int]:
    """song.mid → {part_role: [(start_tick, pitch, velocity, dur_ticks)]}, tpb.

    Parts are identified by MIDI channel, not track name."""
    mid = mido.MidiFile(str(path))
    out: dict[str, list] = {}
    for track in mid.tracks:
        abs_time, active = 0, {}
        for msg in track:
            abs_time += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                active[(msg.channel, msg.note)] = (abs_time, msg.velocity)
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                key = (msg.channel, msg.note)
                if key in active:
                    start, vel = active.pop(key)
                    part = _CHANNEL_PARTS.get(msg.channel)
                    if part is not None:
                        out.setdefault(part, []).append((start, msg.note, vel, abs_time - start))
    for notes in out.values():
        notes.sort()
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


# Actual-distance harshness weights. Only close encounters hurt: a minor 2nd
# (1) is a cluster, a minor 9th (13) is the classic arranging "avoid" interval,
# and an octave-displaced m9 (25) still carries some of that tension. The wider
# mod-12 relatives — maj7 (11), compound maj7 (23) — are consonant color
# (melody riding a 9th/maj7 above the voicing) and counting them buried the
# real problems under lush-but-fine writing.
_CLASH_WEIGHTS = {1: 1.0, 13: 1.0, 25: 0.4}


def _melody_clashes(melody: list, harmony: list, song_beats: float,
                    chord_bars: dict[int, set[int]]) -> float:
    """Harsh collisions between the melody and a simultaneously sounding
    chord/pad note, as weighted clash-beats per 100 beats of song.

    A melody note that is itself a chord tone is never a clash — the melody
    landing on the root of a maj7 chord is normal, consonant writing. What's
    left is a NON-chord melody note at an actual m2/m9 from a sounding chord
    tone (see _CLASH_WEIGHTS), weighted by how long the two actually overlap."""
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
            clash_beats += ov * _CLASH_WEIGHTS.get(abs(m_pitch - h_pitch), 0.0)
    return 100.0 * clash_beats / max(song_beats, 1.0)


def _melody_out_of_key(melody: list, scale_pcs: set[int], chord_bars: dict[int, set[int]],
                       scale_pcs_by_bar: dict[int, set[int]] | None = None) -> float:
    """Sections can modulate (the final-chorus key lift writes its own key into
    song_structure.json), so each note is judged against ITS bar's scale when
    the structure is available — judging a C# chorus against the song's global
    C scale flagged perfectly diatonic melodies."""
    total = bad = 0.0
    for start, pitch, dur in melody:
        total += dur
        pc = pitch % 12
        local_scale = (scale_pcs_by_bar or {}).get(_bar_of(start), scale_pcs)
        if pc in local_scale:
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


# ── instrument-profile checks (Phase 2 of the instrument-identity design) ─────

def _range_violations(tracks: dict[str, list], part_ranges: dict[str, list]) -> float:
    """% of pitched note-time outside the part's INSTRUMENT playable range —
    a sax can't play below its horn, a guitar has no notes below E2."""
    total = bad = 0.0
    for part, notes in tracks.items():
        rng = part_ranges.get(part)
        if not rng:
            continue
        for _, pitch, dur in notes:
            total += dur
            if pitch < rng[0] or pitch > rng[1]:
                bad += dur
    return 100.0 * bad / total if total else 0.0


def _polyphony_violations(tracks: dict[str, list], part_poly: dict[str, int]) -> float:
    """% of sounding time a part exceeds its instrument's polyphony (e.g. a
    monophonic sax holding two notes at once, a 6-string playing 8 voices)."""
    viol = sounding = 0.0
    for part, notes in tracks.items():
        cap = part_poly.get(part)
        if not cap:
            continue
        points: list[tuple[float, int]] = []
        for start, _, dur in notes:
            points.append((start, 1))
            points.append((start + dur, -1))
        points.sort()
        depth, last_t = 0, None
        for t, delta in points:
            if last_t is not None and depth > 0:
                sounding += t - last_t
                if depth > cap:
                    viol += t - last_t
            depth += delta
            last_t = t
    return 100.0 * viol / sounding if sounding else 0.0


# ── structure metrics (songcraft roadmap) ────────────────────────────────────
# Informational, NOT part of the issue score: they measure song-ness (shared
# ideas, escalation, worked transitions), where more/less isn't an error —
# they exist so before/after movement is visible when songcraft features land.

def _motif_recurrence(melody: list, bass: list) -> float:
    """Cosine similarity between melody and bass onset histograms on a 2-bar
    16th grid — "does the bass share the theme's rhythm?" (0..1)."""
    import math

    def hist(notes):
        h = [0.0] * 32
        for start, _, _ in notes:
            h[int(round((start % 8.0) / 0.25)) % 32] += 1
        return h

    a, b = hist(melody), hist(bass)
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    if not na or not nb:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def _load_sections(song_path: Path) -> list[dict]:
    struct = song_path.parent / "song_structure.json"
    if not struct.exists():
        return []
    try:
        return json.loads(struct.read_text(encoding="utf-8"))
    except Exception:
        return []


def _layer_regressions(tracks: dict[str, list], sections: list[dict]) -> int:
    """Count same-type section repeats that carry FEWER active parts than
    their previous occurrence — escalation violations (0 is good)."""
    last_seen: dict[str, int] = {}
    regressions = 0
    for sec in sections:
        stype = sec.get("section_type")
        if stype in (None, "ending"):
            continue
        lo, hi = sec.get("start_bar", 0) * 4.0, (sec.get("start_bar", 0) + sec.get("bars", 0)) * 4.0
        layers = sum(1 for notes in tracks.values()
                     if any(lo <= s < hi for s, _, _ in notes))
        if stype in last_seen and layers < last_seen[stype]:
            regressions += 1
        last_seen[stype] = layers
    return regressions


def _transition_coverage(tracks: dict[str, list], sections: list[dict]) -> float:
    """% of section boundaries carrying at least one transition device:
    a drop (drum silence in the 2 beats before), a build (snare roll), or a
    melodic pickup (the device's 0.42-beat fingerprint)."""
    drums = tracks.get("drums", [])
    melody = tracks.get("melody", [])
    boundaries = [s.get("start_bar", 0) * 4.0 for s in sections[1:]
                  if s.get("section_type") != "ending"]
    if not boundaries:
        return 0.0
    covered = 0
    for b in boundaries:
        drop = drums and not any(b - 2.0 <= s < b - 0.05 for s, _, _ in drums)
        roll = sum(1 for s, p, _ in drums if p in (38, 40) and b - 3.2 <= s < b) >= 6
        pickup = any(abs(d - 0.42) < 0.02 and b - 1.6 <= s < b for s, _, d in melody)
        if drop or roll or pickup:
            covered += 1
    return 100.0 * covered / len(boundaries)


# ── survey ────────────────────────────────────────────────────────────────────

def analyze_song(song_path: Path, key: str, scale: str, style: dict | None = None) -> dict:
    raw_tracks, tpb = _parse_tracks(song_path)
    tracks = {name: _to_beats(notes, tpb) for name, notes in raw_tracks.items()}

    chords = tracks.get("chords", [])
    bass   = tracks.get("bass", [])
    melody = tracks.get("melody", [])
    pads   = tracks.get("pads", [])
    harmony = sorted(chords + pads)

    chord_bars = _chord_pcs_by_bar(chords)
    root_pc = note_name_to_midi(key, 4) % 12
    intervals = SCALE_INTERVALS.get(scale, SCALE_INTERVALS["minor"])
    scale_pcs = {(root_pc + iv) % 12 for iv in intervals}

    # Per-bar scale from the structure file: modulated sections (final-chorus
    # key lift) declare their own key there.
    scale_pcs_by_bar: dict[int, set[int]] = {}
    for sec in _load_sections(song_path):
        sec_key = sec.get("key")
        if not sec_key:
            continue
        sec_root = note_name_to_midi(sec_key, 4) % 12
        sec_pcs = {(sec_root + iv) % 12 for iv in intervals}
        for bar in range(sec.get("start_bar", 0), sec.get("start_bar", 0) + sec.get("bars", 0)):
            scale_pcs_by_bar[bar] = sec_pcs

    song_beats = max((s + d for t in tracks.values() for s, _, d in t), default=0.0)

    # Instrument profile checks: what does each part's INSTRUMENT allow?
    part_ranges: dict[str, list] = {}
    part_poly: dict[str, int] = {}
    if style is not None:
        from app.core.instruments import instrumentation_for
        for part, inst in instrumentation_for(style).items():
            part_ranges[part] = inst["range"]
            part_poly[part] = inst["polyphony"]

    return {
        "bass_out_of_chord_pct": round(_bass_out_of_chord(bass, chord_bars), 1),
        "melody_clash_pct":  round(_melody_clashes(melody, harmony, song_beats, chord_bars), 2),
        "melody_out_of_key_pct": round(_melody_out_of_key(melody, scale_pcs, chord_bars,
                                                          scale_pcs_by_bar), 1),
        "frozen_bass_bars":      _frozen_bass(bass, chord_bars),
        "register_overlap_pct":  round(_register_overlap(chords, melody), 1),
        "dropout_bars":          _dropout_bars(tracks),
        "range_viol_pct":        round(_range_violations(tracks, part_ranges), 2),
        "poly_viol_pct":         round(_polyphony_violations(tracks, part_poly), 2),
        # structure metrics — informational, excluded from the issue score
        "motif_recurrence":      round(_motif_recurrence(melody, bass), 3),
        "layer_regressions":     _layer_regressions(tracks, _load_sections(song_path)),
        "transition_coverage":   round(_transition_coverage(tracks, _load_sections(song_path)), 1),
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
            + m["dropout_bars"] * 1.5
            + m.get("range_viol_pct", 0.0) * 1.0
            + m.get("poly_viol_pct", 0.0) * 0.5)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build songs across styles and analyze the resulting MIDI for cross-part musical problems.")
    ap.add_argument("--styles", nargs="+", default=None, help="style ids (default: all)")
    ap.add_argument("--count", type=int, default=2, help="songs per style (default 2)")
    ap.add_argument("--seed", type=int, default=100, help="base seed; song i uses seed+i")
    ap.add_argument("--template", default="verse_chorus")
    ap.add_argument("--complexity", type=float, default=0.5)
    ap.add_argument("--variation", type=float, default=0.5)
    ap.add_argument("--json", metavar="PATH", default=None, help="also write the full report as JSON")
    ap.add_argument("--prune-exports", type=int, metavar="N", default=None,
                    help="after analysis, delete this run's export folders except the N worst-scoring "
                         "songs (large sweeps would otherwise litter backend/exports; any pruned song "
                         "can be rebuilt exactly from its style+seed)")
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
            metrics = analyze_song(song_path, key, scale, style=style)
            results.append({
                "style": style_id, "seed": seed, "key": f"{key} {scale}",
                "generation_id": resp.generation_id, "path": str(song_path),
                **metrics, "issue_score": round(_score(metrics), 1),
            })
            print(f"  built {style_id} seed={seed} -> {resp.generation_id} (score {results[-1]['issue_score']})")

    ok = [r for r in results if "error" not in r]
    ok.sort(key=lambda r: -r["issue_score"])

    print("\n" + "=" * 100)
    print(f"{'style':<18}{'seed':>6}  {'bassX%':>7}{'clash%':>9}{'offkey%':>9}{'frozen':>8}{'regovr%':>9}{'dropout':>9}{'rngV%':>7}{'polyV%':>8}{'SCORE':>8}  gen_id")
    print("-" * 100)
    for r in ok:
        print(f"{r['style']:<18}{r['seed']:>6}  {r['bass_out_of_chord_pct']:>7}{r['melody_clash_pct']:>9}"
              f"{r['melody_out_of_key_pct']:>9}{r['frozen_bass_bars']:>8}{r['register_overlap_pct']:>9}"
              f"{r['dropout_bars']:>9}{r['range_viol_pct']:>7}{r['poly_viol_pct']:>8}{r['issue_score']:>8}  {r['generation_id']}")

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

    if args.prune_exports is not None and ok:
        import shutil
        keep = {r["generation_id"] for r in ok[:args.prune_exports]}
        pruned = 0
        for r in ok[args.prune_exports:]:
            gen_dir = EXPORTS_DIR / r["generation_id"]
            if gen_dir.is_dir():
                shutil.rmtree(gen_dir, ignore_errors=True)
                r["pruned"] = True
                pruned += 1
        print(f"pruned {pruned} export folder(s); kept the {len(keep)} worst for auditioning")

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2))
        print(f"\nJSON report written to {args.json}")


if __name__ == "__main__":
    main()
