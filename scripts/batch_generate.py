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
Batch generation benchmark and library builder.

Runs N generation attempts per style, scores each one, saves all-green results
to the library (where they improve future quality scoring), and prints a
diagnostic report showing which styles and dimensions need the most work.

Usage (from repo root):
    python scripts/batch_generate.py                        # 100 gens × all styles
    python scripts/batch_generate.py --n 1000              # 1000 gens × all styles
    python scripts/batch_generate.py --styles jazz lofi funk --n 500
    python scripts/batch_generate.py --n 200 --bars 8 --complexity 0.6
    python scripts/batch_generate.py --report-only         # just print current library stats

Green threshold: all 5 dimensions >= 0.82.
All-green generations are auto-saved to the library regardless of --n.
"""

import argparse
import random
import sys
import time
import types
from collections import defaultdict
from pathlib import Path

# ── path setup ────────────────────────────────────────────────────────────────
REPO_ROOT   = Path(__file__).parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.services.style_loader  import load_style, list_styles
from app.services.library       import (
    save_generation as lib_save, is_saved, build_scoring_style, list_library,
)
from app.api.routes_generate    import (
    _run_attempt, _all_green, _GREEN_THRESHOLD,
)

# ── constants ─────────────────────────────────────────────────────────────────
DIMS       = ("harmonic", "register", "rhythm", "density", "mix")
PARTS      = ["chords", "bass", "melody", "drums"]
BARS       = 8
COMPLEXITY = 0.5
VARIATION  = 0.4
MODE       = "arrangement"
KEY        = "C"

# ── helpers ───────────────────────────────────────────────────────────────────

def _make_req(style_id: str, key: str, scale: str, bars: int, complexity: float):
    return types.SimpleNamespace(
        style_id=style_id, key=key, scale=scale,
        bars=bars, complexity=complexity, variation=VARIATION,
        parts=PARTS, mode=MODE,
    )


def _run_one(style_id: str, style: dict, key: str, scale: str,
             bars: int, complexity: float, seed: int,
             scoring_style: dict) -> dict | None:
    """Run a single generation attempt and return quality_raw (or None)."""
    req = _make_req(style_id, key, scale, bars, complexity)
    is_loop        = False
    groove_push    = style.get("groove_push", 0.0)
    sec_dom        = style.get("secondary_dominants", False)
    tritone_sub    = style.get("tritone_substitution", False)
    try:
        all_events, _, _, progression, quality_raw, patterns = _run_attempt(
            req, style, seed, is_loop, groove_push, sec_dom, tritone_sub,
            scoring_style=scoring_style,
        )
    except Exception:
        return None

    if quality_raw is None:
        return None

    # Auto-save all-green results to library
    if _all_green(quality_raw) and not is_saved(style_id, _gen_id(seed)):
        try:
            lib_save(
                gen_id=_gen_id(seed),
                style_id=style_id,
                key=key, scale=scale,
                bpm=style.get("bpm_range", [120, 120])[0],
                bars=bars, seed=seed,
                quality_raw=quality_raw,
                patterns=patterns,
            )
        except Exception:
            pass

    return quality_raw


def _gen_id(seed: int) -> str:
    """Stable 8-char id from seed (avoids UUID overhead)."""
    return f"bt{seed % 10**6:06d}"


def _bar(value: float, width: int = 20) -> str:
    """ASCII progress bar for a 0–1 value."""
    filled = int(value * width)
    color  = "\033[32m" if value >= _GREEN_THRESHOLD else (
             "\033[33m" if value >= 0.52 else "\033[31m")
    return color + "█" * filled + "\033[90m" + "░" * (width - filled) + "\033[0m"


def _dim_color(value: float) -> str:
    color = "\033[32m" if value >= _GREEN_THRESHOLD else (
            "\033[33m" if value >= 0.52 else "\033[31m")
    return f"{color}{value:.2f}\033[0m"


class StyleStats:
    def __init__(self, style_id: str):
        self.style_id  = style_id
        self.totals: list[float]            = []
        self.dims:   dict[str, list[float]] = {d: [] for d in DIMS}
        self.saved   = 0
        self.errors  = 0

    def add(self, q: dict):
        self.totals.append(q["total"])
        for d in DIMS:
            self.dims[d].append(q[d])

    def mean_total(self) -> float:
        return sum(self.totals) / len(self.totals) if self.totals else 0.0

    def mean_dim(self, d: str) -> float:
        vals = self.dims[d]
        return sum(vals) / len(vals) if vals else 0.0

    def pass_rate(self) -> float:
        if not self.totals:
            return 0.0
        green = sum(
            1 for i in range(len(self.totals))
            if all(self.dims[d][i] >= _GREEN_THRESHOLD for d in DIMS)
        )
        return green / len(self.totals)

    def n(self) -> int:
        return len(self.totals)


# ── report ────────────────────────────────────────────────────────────────────

def print_report(all_stats: dict[str, StyleStats], elapsed: float, n_per_style: int):
    total_runs  = sum(s.n()     for s in all_stats.values())
    total_saved = sum(s.saved   for s in all_stats.values())
    total_err   = sum(s.errors  for s in all_stats.values())

    print(f"\n\033[1m{'━'*80}\033[0m")
    print(f"\033[1m  BATCH REPORT — {total_runs} generations in {elapsed:.1f}s "
          f"({total_runs/elapsed:.0f}/s)\033[0m")
    print(f"  Library saves: \033[32m{total_saved}\033[0m   "
          f"Errors: \033[31m{total_err}\033[0m")
    print(f"{'━'*80}")

    # Per-style table
    col_w = 8
    hdr   = f"  {'Style':<18}  {'Total':<7}  {'Pass%':<7}"
    for d in DIMS:
        hdr += f"  {d[:6]:>{col_w}}"
    print(f"\n\033[1m{hdr}\033[0m")
    print("  " + "─" * (len(hdr) - 2))

    # Sort by pass rate descending
    for sid, s in sorted(all_stats.items(), key=lambda x: -x[1].pass_rate()):
        row  = f"  {sid:<18}  "
        row += _dim_color(s.mean_total()) + "   "
        pct  = s.pass_rate() * 100
        pct_color = "\033[32m" if pct >= 50 else ("\033[33m" if pct >= 20 else "\033[31m")
        row += f"{pct_color}{pct:5.1f}%\033[0m  "
        for d in DIMS:
            row += f"  {_dim_color(s.mean_dim(d)):>{col_w + 12}}"
        print(row)

    # Worst dimensions overall
    print("\n\033[1m  WEAKEST DIMENSIONS (mean across all styles)\033[0m")
    dim_means = {
        d: sum(s.mean_dim(d) for s in all_stats.values()) / len(all_stats)
        for d in DIMS
    }
    for d, v in sorted(dim_means.items(), key=lambda x: x[1]):
        bar = _bar(v, 30)
        print(f"    {d:<12}  {bar}  {_dim_color(v)}")

    # Styles needing the most work
    worst_styles = sorted(all_stats.items(), key=lambda x: x[1].pass_rate())[:5]
    print("\n\033[1m  STYLES WITH LOWEST ALL-GREEN PASS RATE\033[0m")
    for sid, s in worst_styles:
        pct = s.pass_rate() * 100
        bar = _bar(s.pass_rate(), 20)
        worst_dim = min(DIMS, key=lambda d: s.mean_dim(d))
        print(f"    {sid:<18}  {bar}  {pct:5.1f}%  (worst: {worst_dim} {_dim_color(s.mean_dim(worst_dim))})")

    print(f"\n{'━'*80}\n")


def print_library_stats():
    """Print current library contents without running any generations."""
    entries = list_library()
    if not entries:
        print("Library is empty.")
        return

    by_style: dict[str, list] = defaultdict(list)
    for e in entries:
        by_style[e["style_id"]].append(e)

    print(f"\n\033[1m  LIBRARY — {len(entries)} saved generations across {len(by_style)} styles\033[0m\n")
    for sid in sorted(by_style):
        elist = by_style[sid]
        totals = [e["quality"]["total"] for e in elist]
        avg = sum(totals) / len(totals)
        print(f"  {sid:<20} {len(elist):>4} saves   avg quality {_dim_color(avg)}")
    print()


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n",           type=int,   default=100, help="Generations per style (default 100)")
    ap.add_argument("--styles",      nargs="*",  default=None, help="Style IDs to test (default: all)")
    ap.add_argument("--bars",        type=int,   default=BARS)
    ap.add_argument("--complexity",  type=float, default=COMPLEXITY)
    ap.add_argument("--report-only", action="store_true", help="Print library stats and exit")
    args = ap.parse_args()

    if args.report_only:
        print_library_stats()
        return

    # Resolve which styles to run
    all_style_meta = list_styles()
    if args.styles:
        run_styles = [m for m in all_style_meta if m["id"] in args.styles]
        missing    = set(args.styles) - {m["id"] for m in run_styles}
        if missing:
            print(f"[warn] Unknown styles: {', '.join(missing)}")
    else:
        run_styles = all_style_meta

    if not run_styles:
        print("No styles to run. Exiting.")
        return

    n          = args.n
    bars       = args.bars
    complexity = args.complexity
    total_runs = n * len(run_styles)

    print("\n\033[1m  GenreGrid batch benchmark\033[0m")
    print(f"  {n} generations × {len(run_styles)} styles = {total_runs} total")
    print(f"  bars={bars}  complexity={complexity}  green≥{_GREEN_THRESHOLD}\n")

    all_stats: dict[str, StyleStats] = {}
    t_start   = time.perf_counter()
    done      = 0

    for meta in run_styles:
        sid   = meta["id"]
        scale = meta.get("default_scale", "minor")
        try:
            style = load_style(sid)
        except Exception as e:
            print(f"  [{sid}] load error: {e}")
            continue

        scoring_style = build_scoring_style(style, sid)
        stats         = StyleStats(sid)
        all_stats[sid] = stats

        saved_this_style = 0
        t0 = time.perf_counter()

        for i in range(n):
            seed = random.randint(0, 2**31 - 1)
            q    = _run_one(sid, style, KEY, scale, bars, complexity, seed, scoring_style)

            if q is None:
                stats.errors += 1
            else:
                stats.add(q)
                if _all_green(q):
                    saved_this_style += 1
                    stats.saved += 1

            done += 1

            # Progress line (overwrite in place)
            elapsed = time.perf_counter() - t_start
            rate    = done / elapsed if elapsed > 0 else 0
            eta     = (total_runs - done) / rate if rate > 0 else 0
            pct     = done / total_runs * 100
            sys.stdout.write(
                f"\r  [{pct:5.1f}%]  {sid:<18}  "
                f"{i+1:>{len(str(n))}}/{n}  "
                f"saves={saved_this_style}  "
                f"ETA {eta:5.0f}s   "
            )
            sys.stdout.flush()

        dt = time.perf_counter() - t0
        pass_pct = stats.pass_rate() * 100
        worst_dim = min(DIMS, key=lambda d: stats.mean_dim(d))

        sys.stdout.write(
            f"\r  {sid:<20}  n={stats.n()}  "
            f"pass={pass_pct:5.1f}%  "
            f"total={stats.mean_total():.3f}  "
            f"saves={stats.saved}  "
            f"worst={worst_dim}({stats.mean_dim(worst_dim):.2f})  "
            f"{dt:.1f}s\n"
        )
        sys.stdout.flush()

        # Refresh scoring style with newly saved examples
        scoring_style = build_scoring_style(style, sid)

    elapsed = time.perf_counter() - t_start
    print_report(all_stats, elapsed, n)


if __name__ == "__main__":
    main()
