# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Song building + per-part song regeneration."""
from app.models.schemas import BuildSongRequest, RegenerateSongPartRequest
from app.api.routes_generate import build_song, regenerate_song_part
from app.core.config import EXPORTS_DIR


def test_build_song_writes_stems_and_meta():
    r = build_song(BuildSongRequest(style_id="lofi", key="C", scale="major", bpm=90,
                                    template="compact", parts=["chords", "bass", "melody", "drums"],
                                    seed=5))
    parts = {f.part for f in r.files}
    assert {"chords", "bass", "melody", "drums", "song"} <= parts
    assert (EXPORTS_DIR / r.generation_id / "song_meta.json").exists()


def test_regenerate_song_part_isolates_the_target():
    """Regenerating one stem changes only that stem; harmony/others stay identical."""
    r = build_song(BuildSongRequest(style_id="lofi", key="C", scale="major", bpm=90,
                                    template="compact", parts=["chords", "bass", "melody", "drums"],
                                    seed=7))
    d = EXPORTS_DIR / r.generation_id
    drums_before = (d / "drums.mid").read_bytes()
    chords_before = (d / "chords.mid").read_bytes()
    song_before = (d / "song.mid").read_bytes()

    fi = regenerate_song_part(RegenerateSongPartRequest(generation_id=r.generation_id, part="drums"))
    assert fi.part == "drums"

    assert (d / "drums.mid").read_bytes() != drums_before      # re-rolled
    assert (d / "chords.mid").read_bytes() == chords_before    # untouched
    assert (d / "song.mid").read_bytes() != song_before        # combined rebuilt


def test_recurring_sections_reuse_the_theme():
    """Verse 2 reuses Verse's theme (with light variation); drums stay fresh."""
    from app.services.style_loader import load_style
    from app.api.routes_generate import _generate_song_sections

    req = BuildSongRequest(style_id="lofi", key="C", scale="major", bpm=90,
                           template="verse_chorus", parts=["chords", "bass", "melody", "drums"],
                           seed=11)
    style = {**load_style("lofi"), "_humanize_scale": 0.5}
    ev, secs, _, _ = _generate_song_sections(req, style, 90, 11, 0, False, False,
                                             style.get("groove_push", 0.0))

    def section_part(name, part):
        s = next(x for x in secs if x["name"] == name)
        a, b = s["start_bar"] * 4, (s["start_bar"] + s["bars"]) * 4
        return {(round(e.start - a, 3), e.pitch) for e in ev[part] if a <= e.start < b}

    # Repeated sections carry the same theme, allowing the light repeat-variation
    # pass (re-humanized velocities, occasional ornaments) to alter some events.
    def overlap(a, b):
        return len(a & b) / max(1, len(a))

    assert overlap(section_part("Verse", "melody"), section_part("Verse 2", "melody")) >= 0.6
    assert overlap(section_part("Chorus", "melody"), section_part("Chorus 2", "melody")) >= 0.6
    assert section_part("Verse", "drums") != section_part("Verse 2", "drums")
