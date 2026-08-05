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

# Voices with no sample directory of their own, played from another voice's set.
# Mirrors BASS_SAMPLE_DIR in frontend/src/soundfonts/bass.ts.
VOICE_SAMPLE_DIR_ALIASES = {
    # No CC0 slap-bass library exists, so slap borrows the fingered Jazz Bass.
    "slap_bass_1": "electric_bass_finger",
}

# Voices that fall through to a generic synth **on purpose**. This is a real gap
# in instrument identity, not an oversight, so it is listed rather than asserted
# away — each entry is a voice the app plays with someone else's timbre.
#
#   clavinet
#       No CC0 or CC-BY multisample has been found: FreePats lists one as "in
#       development" and the only other SFZ carries an unconfirmed license. See
#       docs/LICENSE_AUDIT.md §7. Remove this entry the moment one is sourced —
#       drawbar_organ, accordion, and acoustic_guitar_nylon left this list on
#       2026-08-04 when FreePats CC0 sets were found for them.
#   synth_bass_1
#       Synthesized by choice — it IS a synth, so the app's own oscillator beats
#       a frozen sample of someone else's.
DELIBERATELY_SYNTHESIZED = {
    "clavinet",
    "synth_bass_1",
}


def _sampled_voices() -> set[str]:
    """Voice ids backed by a sample directory on disk (melodic + bass)."""
    voices: set[str] = set()
    for family in ("melodic", "bass"):
        d = _SAMPLES / family
        assert d.is_dir(), f"Missing sample family dir {d}"
        voices |= {p.name for p in d.iterdir() if p.is_dir()}
    assert voices, "Found zero sample directories — the samples tree moved; fix this test"
    voices |= {alias for alias, target in VOICE_SAMPLE_DIR_ALIASES.items() if target in voices}
    return voices


def test_sample_tree_is_present():
    # A moved/renamed samples tree would make the check vacuous; fail loudly.
    assert _SAMPLES.is_dir(), f"Expected frontend sample tree at {_SAMPLES}"


def test_every_registry_voice_is_implemented_by_the_frontend():
    implemented = _sampled_voices() | FRONTEND_SYNTH_VOICES | DELIBERATELY_SYNTHESIZED
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


def test_deliberately_synthesized_list_is_current():
    # Two ways this list rots: a voice gets a real sample set (so the entry is
    # now a lie that hides a working instrument), or the registry stops using it.
    sampled = _sampled_voices()
    now_sampled = DELIBERATELY_SYNTHESIZED & sampled
    assert not now_sampled, (
        f"These voices now have sample sets: {now_sampled}. Drop them from "
        "DELIBERATELY_SYNTHESIZED (and from the 'still synthesized' notes in "
        "DATA_LICENSES.md / docs/LICENSE_AUDIT.md)."
    )
    used = {inst["playback_voice"] for inst in INSTRUMENTS.values()}
    dead = DELIBERATELY_SYNTHESIZED - used
    assert not dead, f"DELIBERATELY_SYNTHESIZED lists voices no instrument uses: {dead}"


def test_synth_family_list_has_no_dead_entries():
    # Guard the allowlist: a synth-family id no registry entry uses is a stale
    # note that will mislead the next reader.
    used = {inst["playback_voice"] for inst in INSTRUMENTS.values()}
    dead = FRONTEND_SYNTH_VOICES - used
    assert not dead, f"FRONTEND_SYNTH_VOICES lists voices no instrument uses: {dead}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
