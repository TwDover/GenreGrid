# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Cross-language drift guard: backend instrument registry ↔ frontend playback.

The registry (``app/core/instruments.py``) is the single source of truth for
instrument identity, and each entry names a ``playback_voice`` the in-app
preview must produce. The frontend implements those voices in two ways, in a
*different* language, so nothing in the type-checker or the Python suite catches
a registry voice the frontend can't build — it would just fall back silently.

A voice is playable when it is either a **sampled voice** (a directory of
samples under ``frontend/public/samples/{melodic,bass}/<voice>/``) or one of the
named **synth families** the player builds procedurally. This test asserts every
registry ``playback_voice`` resolves one of those two ways, so a new instrument
with an unimplemented voice fails here instead of going mute in the app.
"""
from pathlib import Path

import pytest

from app.core.instruments import INSTRUMENTS

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLES = _REPO_ROOT / "frontend" / "public" / "samples"

# Non-sampled voice ids the frontend player builds procedurally. Keep in sync
# with the voice resolution in frontend/src/composables/useMidiPlayer.ts:
#   melody_lead -> makeMelodyLead   (winds/brass articulate lead)
#   synth_lead  -> makeMelodyLead / makeSynthChords (electronic + distorted-guitar)
#   pad_synth   -> makePad          (sustained pad voice)
FRONTEND_SYNTH_VOICES = {"melody_lead", "synth_lead", "pad_synth"}


def _sampled_voices() -> set[str]:
    """Voice ids backed by a sample directory on disk (melodic + bass)."""
    voices: set[str] = set()
    for family in ("melodic", "bass"):
        d = _SAMPLES / family
        assert d.is_dir(), f"Missing sample family dir {d}"
        voices |= {p.name for p in d.iterdir() if p.is_dir()}
    assert voices, "Found zero sample directories — the samples tree moved; fix this test"
    return voices


def test_sample_tree_is_present():
    # A moved/renamed samples tree would make the check vacuous; fail loudly.
    assert _SAMPLES.is_dir(), f"Expected frontend sample tree at {_SAMPLES}"


def test_every_registry_voice_is_implemented_by_the_frontend():
    implemented = _sampled_voices() | FRONTEND_SYNTH_VOICES
    orphans = {
        inst_id: inst["playback_voice"]
        for inst_id, inst in INSTRUMENTS.items()
        if inst["playback_voice"] not in implemented
    }
    assert not orphans, (
        "Registry instruments name a playback_voice the frontend can't build "
        f"(they'll fall back silently in-app): {orphans}. Add a sample set under "
        "frontend/public/samples/, a synth family in the player, or point the "
        "entry at an implemented voice."
    )


def test_synth_family_list_has_no_dead_entries():
    # Guard the allowlist: a synth-family id no registry entry uses is a stale
    # note that will mislead the next reader.
    used = {inst["playback_voice"] for inst in INSTRUMENTS.values()}
    dead = FRONTEND_SYNTH_VOICES - used
    assert not dead, f"FRONTEND_SYNTH_VOICES lists voices no instrument uses: {dead}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
