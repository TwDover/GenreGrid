# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Progression templates must match the requested scale's mode.

Regression tests for a bug that shipped twice, once in each direction: style
JSONs carried major-tonic templates (bare 'I') that could be drawn for
minor-scale requests and vice versa, putting the whole harmony in the parallel
key while the melody stayed in the declared scale — every major-vs-minor-third
pair ground against each other. _choose_progression now filters templates by
tonic mode, and no shipped style may contain a template that states both
tonics at once ('mixed'), which the filter would exclude in every mode.
"""
import glob
import json
from pathlib import Path

from app.api.routes_generate import _choose_progression, _scale_mode, _template_tonic_mode

STYLES_DIR = Path(__file__).parent.parent / "app" / "styles"


def test_template_tonic_mode_classification():
    assert _template_tonic_mode(["i", "iv", "i", "iv"]) == "minor"
    assert _template_tonic_mode(["I", "vi", "IV", "V"]) == "major"
    assert _template_tonic_mode(["ii", "V", "ii", "V"]) is None       # no explicit tonic
    assert _template_tonic_mode(["i", "VI", "i", "I"]) == "mixed"     # contradicts itself
    # Suffixes and accidentals must not create false tonics: 'ivsus2' is a iv,
    # 'bIII' is a flat-three — neither is the tonic.
    assert _template_tonic_mode(["ivsus2", "bVII", "bIII", "v"]) is None


def test_scale_mode_families():
    assert _scale_mode("minor") == "minor"
    assert _scale_mode("dorian") == "minor"
    assert _scale_mode("pentatonic_minor") == "minor"
    assert _scale_mode("blues") == "minor"
    assert _scale_mode("major") == "major"
    assert _scale_mode("mixolydian") == "major"
    assert _scale_mode("lydian") == "major"


def test_choose_progression_respects_requested_scale():
    """A style carrying BOTH major and minor templates must never hand a
    minor-tonic progression to a major-scale request or vice versa."""
    style = {"progression_templates": [
        ["i", "iv", "i", "iv"],
        ["I", "IV", "I", "IV"],
        ["ii", "V", "ii", "V"],   # tonic-free — legal in both modes
    ]}
    for seed in range(50):
        major_prog = _choose_progression(style, use_priors=False, seed=seed, scale="major")
        assert _template_tonic_mode(major_prog) != "minor", major_prog
        minor_prog = _choose_progression(style, use_priors=False, seed=seed, scale="minor")
        assert _template_tonic_mode(minor_prog) != "major", minor_prog


def test_choose_progression_falls_back_when_nothing_matches():
    """A style whose templates ALL mismatch the requested mode still returns
    something rather than crashing (mismatched harmony beats no harmony)."""
    style = {"progression_templates": [["i", "iv", "v", "i"]]}
    prog = _choose_progression(style, use_priors=False, seed=1, scale="major")
    assert prog == ["i", "iv", "v", "i"]


def test_no_shipped_style_has_mixed_tonic_templates():
    """'Mixed' templates are excluded by the filter in EVERY mode — dead data
    at best, a symptom of a typo at worst. None may ship."""
    for path in sorted(glob.glob(str(STYLES_DIR / "*.json"))):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for template in data.get("progression_templates", []):
            assert _template_tonic_mode(template) != "mixed", \
                f"{data.get('id')}: mixed-tonic template {template}"
