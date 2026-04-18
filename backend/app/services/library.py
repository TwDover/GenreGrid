"""
Generation library.

Saves high-quality MIDI generations with their extracted rhythm fingerprints.
As the library grows, those fingerprints are averaged and blended back into the
quality scorer's reference patterns — making the scorer (and therefore the
auto-retry loop) progressively more accurate for each style.

Storage layout:
    library/
        {style_id}/
            {gen_id}.json   ← metadata + extracted patterns
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import DATA_DIR

_logger = logging.getLogger(__name__)

LIBRARY_DIR = DATA_DIR / "library"
LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

# How strongly learned patterns pull away from the style JSON defaults.
# 0.0 = ignore library, 1.0 = ignore style defaults.
_LEARNED_WEIGHT = 0.40
# Minimum saved examples before we start blending.
_MIN_EXAMPLES = 2


def _style_dir(style_id: str) -> Path:
    d = LIBRARY_DIR / style_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_generation(
    gen_id: str,
    style_id: str,
    key: str,
    scale: str,
    bpm: int,
    bars: int,
    seed: int,
    quality_raw: dict,
    patterns: dict,          # {"kick_pattern": [...], "chord_pattern": [...]}
) -> None:
    """Persist a generation's metadata and rhythm fingerprints."""
    entry = {
        "gen_id":   gen_id,
        "style_id": style_id,
        "key":      key,
        "scale":    scale,
        "bpm":      bpm,
        "bars":     bars,
        "seed":     seed,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "quality":  quality_raw,
        "patterns": patterns,
    }
    (_style_dir(style_id) / f"{gen_id}.json").write_text(
        json.dumps(entry, indent=2)
    )


def is_saved(style_id: str, gen_id: str) -> bool:
    return (LIBRARY_DIR / style_id / f"{gen_id}.json").exists()


def list_library(style_id: str | None = None) -> list[dict]:
    """Return all saved entries, newest first, optionally filtered by style."""
    if not LIBRARY_DIR.exists():
        return []
    dirs = (
        [LIBRARY_DIR / style_id] if style_id
        else [d for d in LIBRARY_DIR.iterdir() if d.is_dir()]
    )
    results = []
    for d in dirs:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                results.append(json.loads(f.read_text()))
            except Exception as exc:
                _logger.warning("Skipping malformed library entry %s: %s", f, exc)
    return results


def _get_learned_patterns(style_id: str) -> dict | None:
    """Average rhythm patterns across saved examples for this style."""
    entries = list_library(style_id)
    if len(entries) < _MIN_EXAMPLES:
        return None

    n = len(entries)
    kick_avg  = [0.0] * 16
    chord_avg = [0.0] * 16
    for e in entries:
        pats = e.get("patterns", {})
        for i in range(16):
            kick_avg[i]  += pats.get("kick_pattern",  [0.0] * 16)[i] / n
            chord_avg[i] += pats.get("chord_pattern", [0.0] * 16)[i] / n

    return {"kick_pattern": kick_avg, "chord_pattern": chord_avg, "example_count": n}


def build_scoring_style(style: dict, style_id: str) -> dict:
    """Return a style dict with kick/chord patterns blended with library averages.

    Used only for quality scoring — the generation itself always uses the
    original style dict so no generative behaviour is altered.
    """
    learned = _get_learned_patterns(style_id)
    if not learned:
        return style

    w = _LEARNED_WEIGHT
    scored = dict(style)

    drums_cfg = dict(style.get("drums", {}))
    if "kick_pattern" in drums_cfg:
        sk = drums_cfg["kick_pattern"]
        lk = learned["kick_pattern"]
        drums_cfg["kick_pattern"] = [(1 - w) * s + w * l for s, l in zip(sk, lk)]
        scored["drums"] = drums_cfg

    if "chord_rhythm" in style:
        sc = style["chord_rhythm"]
        lc = learned["chord_pattern"]
        scored["chord_rhythm"] = [(1 - w) * s + w * l for s, l in zip(sc, lc)]

    return scored
