# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Groove feel profiles — the *systematic* microtiming and velocity contour a
real rhythm section plays, as opposed to uniform random jitter.

A feel profile is a per-16th-slot timing offset (beats; + = behind the grid,
laid back; − = ahead, pushed) and velocity factor, given separately for each
drum instrument class (kick / snare / hat / other), plus a bass lag constant
(how far the bass sits behind the kick). Real feel is systematic: the bass sits
a hair behind the kick, hats push ahead, backbeats drag in laid-back styles, and
the hat velocity across a bar is a repeating shape — none of which uniform
jitter can produce.

The canonical form is the fully-expanded 16-slot arrays (what a corpus miner
writes into a style's JSON ``feel`` block). Hand-authored defaults are stored
compactly as archetype *parameters* and synthesised into the same array form, so
a fresh clone benefits with no corpus while mined values simply overwrite them.
"""
from functools import lru_cache

from app.core.constants import DRUM_MAP

_STEPS = 16

# ── drum instrument classes ───────────────────────────────────────────────────
# Feel is authored per class, not per GM pitch — a groove's identity is "the
# backbeat drags, the hats push", regardless of which snare/hat sample is used.
_KICK  = {DRUM_MAP["kick"], 35}
_SNARE = {DRUM_MAP["snare"], DRUM_MAP["clap"], 40, 37}
_HAT   = {DRUM_MAP["closed_hat"], DRUM_MAP["open_hat"], DRUM_MAP["ride"], 44, 22, 26, 53, 59}


def drum_class(pitch: int) -> str:
    if pitch in _KICK:
        return "kick"
    if pitch in _SNARE:
        return "snare"
    if pitch in _HAT:
        return "hat"
    return "other"


# ── hand-authored archetypes ──────────────────────────────────────────────────
# A compact parametric description of a groove feel. `_synth` expands each into
# the per-slot arrays. Offsets are in beats.
_ARCHETYPES: dict[str, dict] = {
    # Head-nod hip-hop / lofi: the backbeat drags noticeably, hats lean ahead,
    # the bass sits well behind the kick — the classic "behind the beat" pocket.
    "laid_back": {
        "kick_lag":          0.004,
        "backbeat_lag":      0.022,
        "hat_push":         -0.010,
        "hat_offbeat_extra": -0.006,
        "swing":             0.010,
        "bass_lag":          0.018,
        "ghost":             0.82,
    },
    # Funk/afrobeat: tight and on top — kick a touch ahead, hats pushed hard,
    # backbeat barely late, ghost-note snares between the backbeats.
    "pushed_funk": {
        "kick_lag":         -0.004,
        "backbeat_lag":      0.006,
        "hat_push":         -0.014,
        "hat_offbeat_extra": -0.004,
        "swing":             0.004,
        "bass_lag":          0.006,
        "ghost":             0.78,
    },
}

# Which styles opt in, and to which archetype. Styles absent here have no feel
# profile and stay byte-identical to pre-feel output.
_STYLE_FEEL: dict[str, str] = {
    "lofi":      "laid_back",
    "boom_bap":  "laid_back",
    "soul":      "laid_back",
    "rnb":       "laid_back",
    "trap_soul": "laid_back",
    "cloud_rap": "laid_back",
    "funk":      "pushed_funk",
    "afrobeats": "pushed_funk",
}


def _synth(a: dict) -> dict:
    """Expand archetype parameters into the canonical per-class 16-slot arrays."""
    kick_t, snare_t, hat_t, other_t = ([0.0] * _STEPS for _ in range(4))
    kick_v, snare_v, hat_v, other_v = ([1.0] * _STEPS for _ in range(4))

    for s in range(_STEPS):
        offbeat = (s % 2 == 1)
        swing   = a["swing"] if offbeat else 0.0
        backbeat = s in (4, 12)          # snare on beats 2 & 4

        kick_t[s]  = a["kick_lag"] + swing
        hat_t[s]   = a["hat_push"] + swing + (a["hat_offbeat_extra"] if offbeat else 0.0)
        other_t[s] = swing
        snare_t[s] = a["backbeat_lag"] if backbeat else swing

        # Repeating velocity contour: strong beats accented, offbeats/ghosts softer.
        kick_v[s]  = 1.0 if s in (0, 8) else 0.96
        snare_v[s] = 1.0 if backbeat else a["ghost"]
        hat_v[s]   = 1.0 if s % 4 == 0 else (a["ghost"] if offbeat else 0.92)
        other_v[s] = 0.9

    def _r(xs):
        return [round(x, 5) for x in xs]

    return {
        "kick":  {"timing": _r(kick_t),  "velocity": _r(kick_v)},
        "snare": {"timing": _r(snare_t), "velocity": _r(snare_v)},
        "hat":   {"timing": _r(hat_t),   "velocity": _r(hat_v)},
        "other": {"timing": _r(other_t), "velocity": _r(other_v)},
        "bass_lag": round(a["bass_lag"], 5),
    }


@lru_cache(maxsize=None)
def default_feel(style_id: str) -> dict | None:
    """The hand-authored feel profile for a style, or None if it has none."""
    arch = _STYLE_FEEL.get(style_id)
    return _synth(_ARCHETYPES[arch]) if arch else None


def feel_for(style: dict) -> dict | None:
    """Resolve a style's feel profile: a mined ``feel`` block in the style JSON
    overlays the hand-authored default (mined drum classes win per-key; the
    authored ``bass_lag`` survives when mining — which never sees the bass —
    doesn't supply one). Returns None only when there's neither."""
    own = style.get("feel")
    default = default_feel(style.get("id", ""))
    if own and default:
        return {**default, **own}       # own's keys (drum classes) override the default's
    return own or default
