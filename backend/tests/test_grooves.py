# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Drum-groove mining + runtime overlay, tested on a synthetic drum corpus."""
import json

from app.core.constants import DRUM_MAP, DRUM_CHANNEL
from app.mining.drums import empty_groove, analyze_drum_song, finalize_groove
from app.mining.midi_io import read_song
from app.services.midi_writer import NoteEvent, write_midi


def _write_groove_song(path, bars: int = 8) -> None:
    """Four-on-the-floor kick, backbeat snare (2 & 4), 8th-note closed hats."""
    ev: list[NoteEvent] = []
    for bar in range(bars):
        b0 = bar * 4.0
        for beat in range(4):                       # kick on every beat (steps 0,4,8,12)
            ev.append(NoteEvent(DRUM_MAP["kick"], b0 + beat, 0.2, 100, DRUM_CHANNEL))
        for beat in (1, 3):                          # snare on beats 2 & 4
            ev.append(NoteEvent(DRUM_MAP["snare"], b0 + beat, 0.2, 110, DRUM_CHANNEL))
        for e8 in range(8):                          # closed hat on every 8th
            ev.append(NoteEvent(DRUM_MAP["closed_hat"], b0 + e8 * 0.5, 0.1, 80, DRUM_CHANNEL))
    write_midi(ev, path, bpm=120)


def test_groove_mining_recovers_pattern(tmp_path):
    groove = empty_groove("house")
    for i in range(5):
        p = tmp_path / f"g{i}.mid"
        _write_groove_song(p)
        assert analyze_drum_song(read_song(p), groove)
    final = finalize_groove(groove)
    d = final["derived"]

    # Four-on-the-floor kick recovered on steps 0,4,8,12
    assert d["kick_pattern"][0] == 1
    assert d["kick_pattern"][4] == 1
    assert d["kick_pattern"][8] == 1
    assert d["kick_pattern"][12] == 1
    assert sum(d["kick_pattern"]) == 4
    # Backbeat on 2 & 4
    assert d["snare_standard_beats"] == [2, 4]
    # Hats present on the 8ths → ~half the 16th slots
    assert 0.4 <= d["hat_density"] <= 0.6
    # Straight performance → ~no swing
    assert d["swing"] < 0.1


def test_groove_overlay_and_runtime(tmp_path, monkeypatch):
    """A groove prior should overlay the style's drums and drive live generation."""
    import app.services.priors as priors
    from app.services.priors import groove_fields_for
    from app.api.routes_generate import _overlay_groove
    from app.models.schemas import GenerateRequest
    from app.api.routes_generate import generate

    # Mine a synthetic groove and install it as the groove for style 'house'
    groove = empty_groove("house")
    for i in range(5):
        p = tmp_path / f"g{i}.mid"
        _write_groove_song(p)
        analyze_drum_song(read_song(p), groove)
    final = finalize_groove(groove)

    grooves_dir = tmp_path / "grooves"
    grooves_dir.mkdir()
    (grooves_dir / "house.json").write_text(json.dumps(final))
    monkeypatch.setattr(priors, "_GROOVES_DIR", grooves_dir)
    priors._groove_cache.clear()

    style = {"id": "house", "drums": {"kick_pattern": [1, 0, 0, 0] * 4, "swing": 0.0}}
    overlaid = _overlay_groove(style, use_priors=True)
    assert overlaid["drums"]["kick_pattern"] == final["derived"]["kick_pattern"]
    assert overlaid["drums"]["snare_standard_beats"] == [2, 4]
    # use_priors=False leaves the style untouched
    assert _overlay_groove(style, use_priors=False) is style
    # groove_fields_for resolves by style id
    assert groove_fields_for({"id": "house"}, True)["kick_pattern"] == final["derived"]["kick_pattern"]

    # End-to-end: generation with the groove prior present produces drums
    r = generate(GenerateRequest(style_id="house", key="C", scale="minor", bpm=120, bars=8,
                                 complexity=0.6, variation=0.4, parts=["drums", "bass"],
                                 mode="arrangement", seed=3, use_priors=True))
    assert any(f.part == "drums" for f in r.files)
    priors._groove_cache.clear()
