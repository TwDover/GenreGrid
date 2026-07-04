# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Load mined statistical priors and sample from them.

A prior is the JSON produced by ``app.mining.corpus.mine_directory``. These
helpers let the generators draw chord progressions (and, later, melodic shapes)
from what real songs of a genre actually do, instead of only hand-written
templates. Priors live in ``backend/app/priors/<genre>.json``.
"""
import json
import random
from pathlib import Path

_PRIORS_DIR = Path(__file__).resolve().parent.parent / "priors"
_GROOVES_DIR = _PRIORS_DIR / "grooves"

_cache: dict[str, dict | None] = {}
_groove_cache: dict[str, dict | None] = {}


def priors_dir() -> Path:
    return _PRIORS_DIR


def prior_exists(prior_name: str) -> bool:
    """True if a mined prior file exists for this name (no parsing)."""
    return bool(prior_name) and (_PRIORS_DIR / f"{prior_name}.json").exists()


def groove_exists(name: str) -> bool:
    """True if a mined drum-groove prior exists for this name."""
    return bool(name) and (_GROOVES_DIR / f"{name}.json").exists()


def load_groove(name: str) -> dict | None:
    if name in _groove_cache:
        return _groove_cache[name]
    path = _GROOVES_DIR / f"{name}.json"
    g = None
    if path.exists():
        try:
            g = json.loads(path.read_text())
        except Exception:
            g = None
    _groove_cache[name] = g
    return g


def groove_fields_for(style: dict, use_priors: bool = True) -> dict | None:
    """The learned drum fields (kick_pattern, snare_standard_beats, hat_density,
    swing, use_ride) for a style, or None. Overlaid onto the style's drums config
    so the drum generator plays a groove learned from real performances."""
    if not use_priors:
        return None
    name = style.get("groove") or style.get("id", "")
    g = load_groove(name)
    if not g:
        return None
    fields = dict(g.get("derived") or {})
    if g.get("fills"):
        fields["fills"] = g["fills"]          # mined section-transition fills
    return fields


def load_prior(genre: str) -> dict | None:
    """Load and cache a genre prior, or None if it doesn't exist."""
    if genre in _cache:
        return _cache[genre]
    path = _PRIORS_DIR / f"{genre}.json"
    prior = None
    if path.exists():
        try:
            prior = json.loads(path.read_text())
        except Exception:
            prior = None
    _cache[genre] = prior
    return prior


def _weighted_choice(counts: dict, rng: random.Random) -> str | None:
    if not counts:
        return None
    keys = list(counts.keys())
    weights = [max(0.0, float(counts[k])) for k in keys]
    total = sum(weights)
    if total <= 0:
        return rng.choice(keys)
    return rng.choices(keys, weights=weights, k=1)[0]


def dominant_mode(prior: dict) -> str:
    keys = prior.get("keys", {})
    return "minor" if keys.get("minor", 0) >= keys.get("major", 0) else "major"


def best_loop(prior: dict) -> list[str] | None:
    """The most common mined 4-bar progression loop, if any is well-supported."""
    loops = prior.get("harmony", {}).get("loops4", {})
    if not loops:
        return None
    token, count = max(loops.items(), key=lambda kv: kv[1])
    if count < 2:            # need at least a couple of occurrences to trust it
        return None
    return token.split(",")


def _harmony_model(prior: dict, mode: str | None) -> dict:
    """Pick the mode-specific harmony model when it has enough data, else pooled."""
    if mode:
        mode_key = "major" if mode == "major" else "minor"
        by_mode = prior.get("harmony_by_mode", {}).get(mode_key, {})
        if sum(by_mode.get("unigram", {}).values()) >= 8:
            return by_mode
    return prior.get("harmony", {})


def sample_progression(
    prior: dict, length: int = 4, seed: int | None = None, mode: str | None = None,
) -> list[str] | None:
    """Sample a chord progression from the mined n-gram model.

    Walks the bigram transition table from a learned starting chord, drawing from
    the model matching `mode` (major/minor) when available so a major-key request
    doesn't get a minor progression. Falls back to None (caller keeps its template)
    when the prior is too sparse to be useful.
    """
    harmony = _harmony_model(prior, mode)
    bigram = harmony.get("bigram", {})
    starts = harmony.get("starts", {})
    unigram = harmony.get("unigram", {})
    if sum(unigram.values()) < 8:        # not enough data — don't override templates
        return None

    rng = random.Random(seed)
    current = _weighted_choice(starts, rng) or _weighted_choice(unigram, rng)
    if current is None:
        return None

    prog = [current]
    for _ in range(length - 1):
        nxt = _weighted_choice(bigram.get(current, {}), rng)
        if nxt is None:
            nxt = _weighted_choice(unigram, rng)
        prog.append(nxt)
        current = nxt
    return prog


def melody_prior_for(prior_name: str, use_priors: bool = True) -> dict | None:
    """Return a style's mined melody model, or None if missing/too sparse."""
    if not use_priors or not prior_name:
        return None
    prior = load_prior(prior_name)
    if not prior:
        return None
    m = prior.get("melody") or {}
    if sum(float(v) for v in m.get("intervals", {}).values()) < 12:
        return None
    return m


def _weighted_int(counter: dict, rng: random.Random) -> int | None:
    items = [(int(k), float(v)) for k, v in counter.items() if float(v) > 0]
    if not items:
        return None
    keys = [k for k, _ in items]
    return rng.choices(keys, weights=[w for _, w in items], k=1)[0]


def sample_melody_interval(melody: dict, prev_interval: int | None, rng: random.Random) -> int | None:
    """Sample a melodic interval (semitones) from the mined model.

    Conditioned on the previous interval via the phrase (interval-bigram) table
    when available, else drawn from the marginal interval distribution.
    """
    if prev_interval is not None:
        row: dict[int, float] = {}
        for k, v in melody.get("interval_bigrams", {}).items():
            try:
                a, b = k.split(",")
            except ValueError:
                continue
            if int(a) == prev_interval:
                row[int(b)] = row.get(int(b), 0.0) + float(v)
        if row:
            keys = list(row)
            return rng.choices(keys, weights=[row[k] for k in keys], k=1)[0]
    return _weighted_int(melody.get("intervals", {}), rng)


def describe(prior: dict) -> str:
    """Human-readable summary of a mined prior."""
    h = prior.get("harmony", {})
    m = prior.get("melody", {})
    uni = h.get("unigram", {})
    top_chords = sorted(uni.items(), key=lambda kv: -kv[1])[:6]
    loops = h.get("loops4", {})
    top_loops = sorted(loops.items(), key=lambda kv: -kv[1])[:3]
    ints = m.get("intervals", {})
    top_ints = sorted(ints.items(), key=lambda kv: -int(kv[1]))[:5]
    lines = [
        f"genre={prior.get('genre')} songs={prior.get('songs')} "
        f"(used {prior.get('files_used', '?')}/{prior.get('files_seen', '?')} files)",
        f"key bias: {prior.get('keys')}",
        f"top chords: {', '.join(f'{t}×{c}' for t, c in top_chords)}",
        f"top 4-loops: {'; '.join(f'{l} ×{c}' for l, c in top_loops) or '(none)'}",
        f"top melodic intervals (semitones): "
        f"{', '.join(f'{i}:{c}' for i, c in top_ints) or '(none)'}",
    ]
    return "\n".join(lines)
