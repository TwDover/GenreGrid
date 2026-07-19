# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""The library learns the USER's taste, not just the scorer's (roadmap-2 item 9):
user-kept generations outweigh merely high-scoring ones, and thumbs-down removes
a generation's influence entirely."""
import app.services.library as lib


def _redirect(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "LIBRARY_DIR", tmp_path)


def test_thumbs_up_outweighs_high_scoring_autosaves(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    A = [1, 0, 0, 0] * 4          # scorer-kept pattern
    B = [0, 0, 1, 0] * 4          # user-kept pattern
    lib.save_generation("g1", "funk", "C", "minor", 120, 8, 1, {"total": 0.9},
                        {"kick_pattern": A, "chord_pattern": A})
    lib.save_generation("g2", "funk", "C", "minor", 120, 8, 2, {"total": 0.9},
                        {"kick_pattern": A, "chord_pattern": A})
    lib.save_generation("g3", "funk", "C", "minor", 120, 8, 3, {"total": 0.6},
                        {"kick_pattern": B, "chord_pattern": B}, keep=2.5, source="thumbs_up")

    learned = lib._get_learned_patterns("funk")
    # One thumbs-up (weight 2.5) outweighs two auto-saves (1.0 each): the B slot wins.
    assert learned["kick_pattern"][2] > learned["kick_pattern"][0]


def test_thumbs_down_removes_influence(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    A = [1, 0, 0, 0] * 4
    B = [0, 0, 1, 0] * 4
    for gid in ("g1", "g2"):
        lib.save_generation(gid, "funk", "C", "minor", 120, 8, 1, {"total": 0.9},
                            {"kick_pattern": A, "chord_pattern": A})
    lib.save_generation("bad", "funk", "C", "minor", 120, 8, 9, {"total": 0.9},
                        {"kick_pattern": B, "chord_pattern": B})
    assert lib.exclude_generation("funk", "bad") is True
    learned = lib._get_learned_patterns("funk")
    assert learned["kick_pattern"][2] == 0.0        # bad's pattern no longer counts
    assert learned["example_count"] == 2


def test_resave_keeps_the_stronger_signal(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    A = [1, 0, 0, 0] * 4
    lib.save_generation("g1", "funk", "C", "minor", 120, 8, 1, {"total": 0.9},
                        {"kick_pattern": A, "chord_pattern": A}, keep=2.5, source="thumbs_up")
    # A later scorer auto-save must not demote the explicit user keep.
    lib.save_generation("g1", "funk", "C", "minor", 120, 8, 1, {"total": 0.9},
                        {"kick_pattern": A, "chord_pattern": A})
    entry = lib.list_library("funk")[0]
    assert entry["keep"] == 2.5 and entry["source"] == "thumbs_up"
