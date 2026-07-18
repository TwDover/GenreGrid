# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Arrangement dynamics: the built song must breathe.

apply_arrangement_dynamics adds the classic dropouts — pre-chorus drop,
bridge breakdown (sometimes bass too), thinned second verse (sometimes
chords too), melody late-entry in verse 1, and arp growth into the final
chorus — seeded from the song's base_seed so every regeneration flow
reproduces the same arrangement.
"""
from app.core.arrangement import apply_arrangement_dynamics
from app.services.midi_writer import NoteEvent

SECTIONS = [
    {"name": "Verse",    "section_type": "verse",  "start_bar": 0,  "bars": 8},
    {"name": "Chorus",   "section_type": "chorus", "start_bar": 8,  "bars": 8},
    {"name": "Verse 2",  "section_type": "verse",  "start_bar": 16, "bars": 8},
    {"name": "Bridge",   "section_type": "bridge", "start_bar": 24, "bars": 8},
    {"name": "Chorus 2", "section_type": "chorus", "start_bar": 32, "bars": 8},
]
TOTAL_BEATS = 40 * 4

# Device windows implied by SECTIONS (beats)
V1_ENTRY = (0.0, 8.0)        # verse-1 melody late entry: first 2 bars
CH1_DROP = (30.0, 32.0)      # 2 beats before chorus 1
CH1_ARP_HALF = (32.0, 48.0)  # first half of chorus 1
V2_THIN = (64.0, 72.0)       # first 2 bars of verse 2
BR_HALF = (96.0, 112.0)      # first half of the bridge
CH2_DROP = (126.0, 128.0)    # 2 beats before chorus 2


def _make_events():
    """Dense synthetic song so every strip window has material to remove."""
    drums, bass, arp = [], [], []
    beat = 0.0
    while beat < TOTAL_BEATS:
        drums.append(NoteEvent(36, beat, 0.1, 100, 9))            # kick
        if int(beat) % 4 in (1, 3):
            drums.append(NoteEvent(38, beat, 0.1, 95, 9))         # snare
        drums.append(NoteEvent(42, beat, 0.05, 60, 9))            # hat
        drums.append(NoteEvent(42, beat + 0.5, 0.05, 50, 9))      # hat offbeat
        bass.append(NoteEvent(36, beat, 0.9, 90, 1))
        arp.append(NoteEvent(76, beat, 0.2, 70, 3))
        beat += 1.0
    return {
        "drums": drums, "bass": bass, "arpeggio": arp,
        "melody": [NoteEvent(72, float(b), 0.5, 80, 2) for b in range(0, TOTAL_BEATS, 2)],
        "chords": [NoteEvent(60, float(b), 3.5, 70, 0) for b in range(0, TOTAL_BEATS, 4)],
    }


def _in(events, part, lo, hi, pitches=None):
    return [e for e in events[part]
            if lo <= e.start < hi and (pitches is None or e.pitch in pitches)]


def test_every_device_fires_across_seeds_and_untouched_elsewhere():
    seen = {k: False for k in ("drop", "breakdown", "deep_breakdown",
                               "thin_v2", "chords_out", "late_entry", "arp_half")}
    for seed in range(60):
        ev = _make_events()
        apply_arrangement_dynamics(ev, SECTIONS, base_seed=seed)

        if not _in(ev, "drums", *CH1_DROP) or not _in(ev, "drums", *CH2_DROP):
            seen["drop"] = True
        if not _in(ev, "drums", *BR_HALF):
            seen["breakdown"] = True
            if not _in(ev, "bass", *BR_HALF):
                seen["deep_breakdown"] = True
        if not _in(ev, "drums", *V2_THIN, pitches={38}) and _in(ev, "drums", *V2_THIN, pitches={36}):
            seen["thin_v2"] = True
            if not _in(ev, "chords", *V2_THIN):
                seen["chords_out"] = True
        if not _in(ev, "melody", *V1_ENTRY):
            seen["late_entry"] = True
        if not _in(ev, "arpeggio", *CH1_ARP_HALF):
            seen["arp_half"] = True

        # Regions no device targets stay bit-identical
        fresh = _make_events()
        assert len(_in(ev, "drums", 8.0, 30.0)) == len(_in(fresh, "drums", 8.0, 30.0))
        # Melody may only ever be stripped inside the verse-1 entry window
        assert len(_in(ev, "melody", V1_ENTRY[1], TOTAL_BEATS)) == \
               len(_in(fresh, "melody", V1_ENTRY[1], TOTAL_BEATS))
        # The final chorus's SECOND half always keeps its full arpeggio (the
        # breakdown-final-chorus device may strip the first half, but the back
        # half is the payoff and no device touches it)
        assert len(_in(ev, "arpeggio", 144.0, 160.0)) == len(_in(fresh, "arpeggio", 144.0, 160.0))

    missing = [k for k, v in seen.items() if not v]
    assert not missing, f"devices never fired in 60 seeds: {missing}"


def test_dynamics_are_deterministic_per_seed():
    """Regeneration flows replay the same base_seed — the arrangement must be
    byte-identical or regenerated stems would disagree with the song on disk."""
    for seed in (3, 17, 29):
        a, b = _make_events(), _make_events()
        apply_arrangement_dynamics(a, SECTIONS, base_seed=seed)
        apply_arrangement_dynamics(b, SECTIONS, base_seed=seed)
        for part in a:
            assert [(e.pitch, e.start) for e in a[part]] == [(e.pitch, e.start) for e in b[part]], \
                f"seed {seed}: {part} differs between identical runs"


def test_single_chorus_song_keeps_its_arp():
    """Arp growth needs a later, bigger chorus to grow INTO — a song with one
    chorus must never lose arpeggio content."""
    sections = [
        {"name": "Verse",  "section_type": "verse",  "start_bar": 0, "bars": 8},
        {"name": "Chorus", "section_type": "chorus", "start_bar": 8, "bars": 8},
    ]
    for seed in range(20):
        ev = _make_events()
        before = len(_in(ev, "arpeggio", 32.0, 64.0))
        apply_arrangement_dynamics(ev, sections, base_seed=seed)
        # inside-the-chorus content only: the pre-chorus full-band stop may
        # legitimately clip the 2-beat drop window before it
        assert len(_in(ev, "arpeggio", 32.0, 64.0)) == before


def test_first_chorus_at_song_start_is_never_dropped_into():
    """A chorus in the first two bars has no run-up to cut — the drop must
    not strip anything before beat 8."""
    sections = [{"name": "Chorus", "section_type": "chorus", "start_bar": 1, "bars": 8}]
    for seed in range(20):
        ev = _make_events()
        before = len(ev["drums"])
        apply_arrangement_dynamics(ev, sections, base_seed=seed)
        assert len(ev["drums"]) == before


def test_melodic_pickups_lead_into_sections():
    from app.core.arrangement import apply_melodic_pickups

    style = {"id": "t"}
    saw_pickup = False
    for seed in range(30):
        # Sparse melody: one note ON each section downbeat, silence before it —
        # a free runway into every boundary.
        ev = {"melody": [NoteEvent(67, float(s["start_bar"] * 4), 1.0, 80, 2) for s in SECTIONS]}
        apply_melodic_pickups(ev, SECTIONS, base_seed=seed, scale="minor", style=style)
        extras = [e for e in ev["melody"] if e.duration < 0.5]
        if extras:
            saw_pickup = True
            for e in extras:
                # pickups sit in the last 1.5 beats before some section boundary
                dist = min(s["start_bar"] * 4 - e.start for s in SECTIONS
                           if s["start_bar"] * 4 > e.start)
                assert 0.3 < dist <= 1.6, f"seed {seed}: pickup at {e.start} not before a boundary"
                # and never collide with the target downbeat note
                assert e.start + e.duration <= dist + e.start + 1e-6
    assert saw_pickup, "no pickups fired in 30 seeds"


def test_pickups_respect_occupied_runway_and_determinism():
    from app.core.arrangement import apply_melodic_pickups

    style = {"id": "t"}
    # Runway occupied: a held cadence note ringing right up to every boundary
    for seed in range(20):
        ev = {"melody": []}
        for s in SECTIONS:
            b = s["start_bar"] * 4.0
            ev["melody"].append(NoteEvent(67, b, 1.0, 80, 2))
            if b >= 4:
                ev["melody"].append(NoteEvent(64, b - 3.0, 2.9, 70, 2))  # rings to b-0.1
        before = len(ev["melody"])
        apply_melodic_pickups(ev, SECTIONS, base_seed=seed, scale="minor", style=style)
        assert len(ev["melody"]) == before, f"seed {seed}: pickup added over a held note"

    # Determinism: same seed → identical pickups
    for seed in (5, 9):
        a = {"melody": [NoteEvent(67, float(s["start_bar"] * 4), 1.0, 80, 2) for s in SECTIONS]}
        b = {"melody": [NoteEvent(67, float(s["start_bar"] * 4), 1.0, 80, 2) for s in SECTIONS]}
        apply_melodic_pickups(a, SECTIONS, base_seed=seed, scale="minor", style=style)
        apply_melodic_pickups(b, SECTIONS, base_seed=seed, scale="minor", style=style)
        assert [(e.pitch, e.start) for e in a["melody"]] == [(e.pitch, e.start) for e in b["melody"]]
