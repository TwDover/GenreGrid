# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Instrument registry + per-style instrumentation validation.

Phase 1 of docs/instrument-identity-design.md: every built-in style binds all
six part roles to registry instruments, the derived GM programs exactly match
the legacy _STYLE_PROGRAMS behavior (proving the migration changed labels, not
sound), and no monophonic instrument holds a chord-bearing role.
"""
import glob
import json
from pathlib import Path

from app.core.instruments import (INSTRUMENTS, PART_ROLES, POLYPHONIC_ROLES,
                                  gm_programs_for, instrumentation_for, track_display_name)
from app.services.mixdown import _DEFAULT_PROGRAMS, _STYLE_PROGRAMS, part_midi_meta

STYLES_DIR = Path(__file__).parent.parent / "app" / "styles"


def _all_styles():
    for path in sorted(glob.glob(str(STYLES_DIR / "*.json"))):
        yield json.loads(Path(path).read_text(encoding="utf-8"))


def test_registry_entries_are_complete():
    for inst_id, inst in INSTRUMENTS.items():
        assert inst["display_name"], inst_id
        assert 0 <= inst["gm_program"] <= 127, inst_id
        lo, hi = inst["range"]
        assert 0 <= lo < hi <= 127, inst_id
        assert inst["polyphony"] >= 1, inst_id
        assert inst["sustain"] in ("decay", "sustain", "ring"), inst_id


def test_every_builtin_style_binds_all_roles():
    for style in _all_styles():
        block = style.get("instrumentation")
        assert block, f"{style['id']}: missing instrumentation block"
        for role in PART_ROLES:
            assert role in block, f"{style['id']}: role {role!r} unbound"
            assert block[role] in INSTRUMENTS, \
                f"{style['id']}: unknown instrument {block[role]!r} for {role}"


def test_instrumentation_programs_match_legacy_exactly():
    """The migration must be inaudible: instrument-derived GM programs equal
    what _STYLE_PROGRAMS/_DEFAULT_PROGRAMS produced before."""
    for style in _all_styles():
        legacy = {**_DEFAULT_PROGRAMS, **_STYLE_PROGRAMS.get(style["id"], {})}
        derived = gm_programs_for(style)
        for role in PART_ROLES:
            assert derived[role] == legacy[role], \
                f"{style['id']}/{role}: derived {derived[role]} != legacy {legacy[role]}"


def test_no_monophonic_instrument_on_polyphonic_role():
    for style in _all_styles():
        insts = instrumentation_for(style)
        for role in POLYPHONIC_ROLES:
            inst = insts.get(role)
            if inst is not None:
                assert inst["polyphony"] >= 3, \
                    f"{style['id']}: {role} bound to near-monophonic {inst['display_name']}"


def test_track_names_and_fallbacks():
    style = {"id": "jazz", "instrumentation": {"melody": "alto_sax"}}
    assert track_display_name(style, "melody") == "Alto Sax (melody)"
    assert track_display_name(style, "chords") is None          # unbound role
    assert track_display_name({}, "melody") is None             # no block at all

    # Unknown instrument id degrades gracefully (custom-style typo)
    bad = {"id": "x", "instrumentation": {"melody": "no_such_instrument"}}
    assert track_display_name(bad, "melody") is None

    # part_midi_meta keeps full legacy behavior for styles without a block
    programs, names = part_midi_meta({"id": "jazz"})
    assert programs["melody"] == 65 and names == {}
