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


def test_resolve_avoid_notes():
    from app.api.routes_generate import _resolve_avoid_notes
    from app.services.midi_writer import NoteEvent

    c_minor_pcs = {0, 2, 3, 5, 7, 8, 10}
    scales = [(0.0, 16.0, c_minor_pcs)]
    harmony = [NoteEvent(pitch=63, start=0.0, duration=4.0, velocity=70, channel=0)]  # Eb4 held

    # Sustained D4 a m2 under the sounding Eb4 (non-chord tone) → must move to
    # an in-scale pitch that clears the m2/m9.
    held = [NoteEvent(pitch=62, start=1.0, duration=1.0, velocity=80, channel=2)]
    out = _resolve_avoid_notes(held, harmony, scales)
    assert out[0].pitch != 62
    assert out[0].pitch % 12 in c_minor_pcs
    assert abs(out[0].pitch - 63) not in (1, 13)
    assert (out[0].start, out[0].duration, out[0].velocity) == (1.0, 1.0, 80)

    # A short passing D4 (16th) is normal melodic motion — untouched.
    passing = [NoteEvent(pitch=62, start=1.0, duration=0.25, velocity=80, channel=2)]
    assert _resolve_avoid_notes(passing, harmony, scales)[0].pitch == 62

    # A melody note doubling a harmony pitch class is consonant — untouched
    # even though another harmony tone is a semitone away.
    harmony2 = harmony + [NoteEvent(pitch=62, start=0.0, duration=4.0, velocity=70, channel=0)]
    doubling = [NoteEvent(pitch=74, start=1.0, duration=1.0, velocity=80, channel=2)]  # D5, doubles D4
    assert _resolve_avoid_notes(doubling, harmony2, scales)[0].pitch == 74

    # No harsh interval at all (D5 = compound maj7 above Eb4) — untouched.
    wide = [NoteEvent(pitch=74, start=1.0, duration=1.0, velocity=80, channel=2)]
    assert _resolve_avoid_notes(wide, harmony, scales)[0].pitch == 74
