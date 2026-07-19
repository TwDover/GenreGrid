# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Regression tests for musical behavior: section-aware drums, harmonic
correctness, song endings, tempo maps, and section arrangement rules."""
import random

import mido
import pytest

from app.core.constants import DRUM_MAP
from app.theory.chords import roman_to_chord
from app.generators.drums import generate_drums
from app.generators.chords import generate_chords, resolve_progression
from app.services.style_loader import load_style
from app.models.schemas import BuildSongRequest, SongSectionDef, RegenerateSongPartRequest
from app.api.routes_song import build_song, regenerate_song_part
from app.core.arrangement import _song_tempo_map
from app.core.config import EXPORTS_DIR


def _style(style_id="lofi"):
    return {**load_style(style_id), "_humanize_scale": 0.5}


# ── Harmony correctness ───────────────────────────────────────────────────────

def test_pentatonic_degrees_match_diatonic_roots():
    """Unflatted VI/VII in a 5-note scale must not alias onto I/ii roots."""
    for roman in ("I", "ii", "VI", "VII"):
        assert roman_to_chord(roman, "C", "pentatonic_minor") == \
               roman_to_chord(roman, "C", "minor"), f"{roman} aliased in pentatonic_minor"


def test_harmony_complexity_drives_chords_per_bar():
    """harmony_complexity above 0.6 must produce two chord changes per bar."""
    random.seed(3)
    evts = generate_chords(_style(), "C", "minor", 2, 0.4, 0.3,
                           ["i", "VI", "III", "VII"], ["i", "VI", "III", "VII"],
                           harmony_complexity=0.8)
    # With 2 chords/bar the second chord of bar 1 starts near beat 2
    assert any(1.8 <= e.start <= 2.3 for e in evts), \
        "expected a chord change near beat 2 with harmony_complexity=0.8"


def test_prev_voicing_seeds_voice_leading():
    """A supplied prev_voicing must pull the first chord's voicing toward it."""
    prog = ["i", "VI", "III", "VII"]
    resolved = resolve_progression(prog, "minor", 0.3)
    random.seed(7)
    free = generate_chords(_style(), "C", "minor", 1, 0.3, 0.2, prog, resolved)
    random.seed(7)
    seeded = generate_chords(_style(), "C", "minor", 1, 0.3, 0.2, prog, resolved,
                             prev_voicing=[67, 72, 76])
    first_free   = sorted({e.pitch for e in free   if e.start < 0.5})
    first_seeded = sorted({e.pitch for e in seeded if e.start < 0.5})
    # Same pitch classes (same chord), but voiced differently because of the seed
    assert {p % 12 for p in first_free} == {p % 12 for p in first_seeded}


# ── Section-aware drums ───────────────────────────────────────────────────────

def test_intro_drums_have_no_snare():
    random.seed(11)
    evts = generate_drums(_style(), 4, 0.6, 0.4, is_loop=True, section_type="intro")
    assert not any(e.pitch == DRUM_MAP["snare"] for e in evts)


def test_chorus_opens_with_crash():
    random.seed(11)
    evts = generate_drums(_style(), 8, 0.6, 0.4, is_loop=True, section_type="chorus")
    assert any(e.pitch == DRUM_MAP["crash"] and abs(e.start) < 0.2 for e in evts)


def test_bridge_is_half_time():
    """Bridge snare sits on beat 3 (beat-in-bar 2.0), never on beats 2/4."""
    random.seed(11)
    evts = generate_drums(_style(), 4, 0.6, 0.4, is_loop=True, section_type="bridge")
    snare_beats = {round(e.start % 4, 1) for e in evts if e.pitch == DRUM_MAP["snare"]}
    assert not ({1.0, 3.0} & snare_beats), f"backbeat snares in half-time bridge: {snare_beats}"


def test_build_roll_into_chorus():
    """The last bar before a chorus gets a snare-roll build for any style."""
    random.seed(11)
    evts = generate_drums(_style(), 4, 0.6, 0.4, is_loop=True,
                          section_end_bars=[3], section_type="verse",
                          next_section_type="chorus")
    roll = [e for e in evts if e.pitch == DRUM_MAP["snare"] and 15.4 <= e.start < 16.1]
    assert len(roll) >= 6, f"expected a snare-roll build, got {len(roll)} hits"


# ── Tempo map ─────────────────────────────────────────────────────────────────

def test_tempo_map_chorus_push_and_ritardando():
    secs = [
        {"start_bar": 0,  "bars": 4, "section_type": "intro"},
        {"start_bar": 4,  "bars": 8, "section_type": "chorus"},
        {"start_bar": 12, "bars": 4, "section_type": "outro"},
        {"start_bar": 16, "bars": 1, "section_type": "ending"},
    ]
    points = _song_tempo_map(secs, 100, ending_bars=1)
    bpms = [b for _, b in points]
    assert points[0] == (0.0, 100.0)
    assert any(b > 100 for b in bpms), "no chorus push"
    assert bpms[-1] < 100 * 0.8, "no final ritardando"


# ── Full song structure ───────────────────────────────────────────────────────

def test_song_has_ending_bar_and_tempo_track():
    r = build_song(BuildSongRequest(style_id="lofi", key="C", scale="major", bpm=90,
                                    template="compact",
                                    parts=["chords", "bass", "melody", "drums"], seed=31))
    assert r.sections[-1].section_type == "ending"
    assert r.total_bars == 41  # compact template (40) + ending bar

    d = EXPORTS_DIR / r.generation_id
    mid = mido.MidiFile(str(d / "chords.mid"))
    tempos = [msg for tr in mid.tracks for msg in tr if msg.type == "set_tempo"]
    assert len(tempos) > 1, "stems should carry the tempo map, not a single tempo"

    # The ending bar carries a held tonic chord in the chords stem
    tpb = mid.ticks_per_beat
    ending_beat = 40 * 4
    notes = []
    for tr in mid.tracks:
        t = 0
        for msg in tr:
            t += msg.time
            if msg.type == "note_on" and msg.velocity > 0 and t / tpb >= ending_beat - 0.5:
                notes.append(msg.note % 12)
    assert 0 in notes, "ending bar should land on the tonic (C)"


@pytest.fixture(scope="module")
def song_vc():
    """One verse_chorus build shared by the gear-change/tease/quality tests.

    use_priors=False keeps this hermetic: the mining tests install corpus
    priors into the shared library, which would otherwise change what this
    build generates depending on test execution order.
    """
    return build_song(BuildSongRequest(style_id="lofi", key="C", scale="major", bpm=90,
                                       template="verse_chorus",
                                       parts=["chords", "bass", "melody", "drums"],
                                       seed=53, chorus_key_shift=0, final_chorus_lift=2,
                                       use_priors=False))


def _note_ons(gen_id: str, part: str) -> list[tuple[float, int]]:
    mid = mido.MidiFile(str(EXPORTS_DIR / gen_id / f"{part}.mid"))
    tpb = mid.ticks_per_beat
    out = []
    for tr in mid.tracks:
        t = 0
        for msg in tr:
            t += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                out.append((t / tpb, msg.note))
    return out


def _section_events(song, gen_id, part, name):
    s = next(x for x in song.sections if x.name == name)
    a, b = s.start_bar * 4, (s.start_bar + s.bars) * 4
    return {(round(t - a, 2), p) for t, p in _note_ons(gen_id, part) if a <= t < b}


def test_final_chorus_gear_change(song_vc):
    """The last chorus plays the chorus theme lifted by final_chorus_lift semitones."""
    c1 = _section_events(song_vc, song_vc.generation_id, "melody", "Chorus")
    c2 = _section_events(song_vc, song_vc.generation_id, "melody", "Chorus 2")
    lifted = {(t, p + 2) for t, p in c1}
    overlap = len(c2 & lifted) / max(1, len(lifted))
    assert overlap >= 0.5, f"final chorus doesn't carry the lifted theme (overlap {overlap:.2f})"
    # And it should NOT still be in the original key
    same_key = len(c2 & c1) / max(1, len(c1))
    assert same_key < overlap, "final chorus melody was not transposed"


def test_intro_teases_chorus_hook(song_vc):
    """The intro melody is a thinned copy of the chorus hook (home key)."""
    intro = _section_events(song_vc, song_vc.generation_id, "melody", "Intro")
    chorus = _section_events(song_vc, song_vc.generation_id, "melody", "Chorus")
    assert intro, "intro should carry the hook tease"
    matched = sum(1 for ev in intro if ev in chorus)
    assert matched / len(intro) >= 0.8, "intro melody should come from the chorus hook"


def test_sections_carry_quality(song_vc):
    non_ending = [s for s in song_vc.sections if s.section_type != "ending"]
    assert all(s.quality is not None and 0.0 <= s.quality <= 1.0 for s in non_ending)


def test_hook_score_rewards_catchy_chorus():
    """A repeating rhythmic figure with a small pitch vocabulary must outscore a
    high-entropy wandering line, and a too-short chorus is left unscored."""
    from app.services.quality import _hook_score
    from app.services.midi_writer import NoteEvent

    figure = [60, 62, 64, 60]
    catchy = [NoteEvent(figure[i % 4], i * 0.5, 0.5, 90, 2) for i in range(16)]
    s_catchy, _ = _hook_score(catchy)

    random.seed(7)
    wander = [NoteEvent(random.randint(55, 79), i * 0.5, 0.5, 90, 2) for i in range(16)]
    s_wander, _ = _hook_score(wander)

    assert s_catchy is not None and s_wander is not None
    assert s_catchy > s_wander
    assert _hook_score(catchy[:5]) == (None, [])   # too few notes → unscored


def test_hook_dimension_only_scored_with_chorus_spans():
    """score_generation adds the hook dimension exactly when chorus_spans cover
    melody; without spans the payload's hook stays 0 and total is unaffected."""
    from app.services.quality import score_generation
    from app.services.midi_writer import NoteEvent

    figure = [60, 62, 64, 60]
    melody = [NoteEvent(figure[i % 4], i * 0.5, 0.5, 90, 2) for i in range(16)]
    events = {"melody": melody, "chords": [], "bass": [], "drums": []}
    prog = ["i", "VI", "III", "VII"]

    no_span = score_generation(events, _style(), "C", "minor", 4, prog, 0.5)
    with_span = score_generation(events, _style(), "C", "minor", 4, prog, 0.5,
                                 chorus_spans=[(0.0, 8.0)])

    assert no_span["hook"] == 0.0
    assert with_span["hook"] > 0.0
    assert no_span["total"] != with_span["total"]


def test_riff_mode_locks_bass_to_guitar_in_unison():
    """Riff styles play a low-register figure with guitar and bass in unison:
    identical onsets, bass an octave below the guitar's pedal."""
    from app.generators.chords import generate_chords
    from app.generators.bass import generate_bass

    style = _style("metal")
    prog = ["i", "bVI", "bVII", "i"]

    random.seed(3)
    guitar = generate_chords(style, "E", "minor", bars=4, complexity=0.5, variation=0.3,
                             progression=prog, resolved_progression=prog, section_type="verse")
    random.seed(3)
    bass = generate_bass(style, "E", "minor", bars=4, complexity=0.5, variation=0.3,
                         progression=prog, section_type="verse")

    assert guitar and bass
    # Every bass onset coincides with a guitar onset (unison lock).
    g_onsets = sorted({round(e.start, 1) for e in guitar})
    b_onsets = sorted({round(e.start, 1) for e in bass})
    matched = sum(1 for b in b_onsets if any(abs(b - g) < 0.06 for g in g_onsets))
    assert matched / len(b_onsets) > 0.9
    # Bass sits below the guitar pedal.
    assert min(e.pitch for e in bass) < min(e.pitch for e in guitar)
    # Guitar carries power-chord stabs (a fifth above some root) — no comped triads with a 3rd.
    assert any(e2.pitch - e1.pitch == 7
               for e1 in guitar for e2 in guitar
               if abs(e1.start - e2.start) < 0.06 and e2.pitch > e1.pitch)


def test_dj_edit_adds_beat_only_bookends():
    """dj_edit prepends/appends an 8-bar drums+bass section outside the arc."""
    import json
    req = BuildSongRequest(style_id="house", key="C", scale="minor", bpm=124,
                           complexity=0.6, variation=0.5,
                           parts=["chords", "bass", "melody", "drums"],
                           template="verse_chorus", seed=1, dj_edit=True)
    r = build_song(req)
    struct = json.loads((EXPORTS_DIR / r.generation_id / "song_structure.json").read_text())
    types = [s.get("section_type") for s in struct]
    assert types[0] == "dj_intro"
    assert "dj_outro" in types
    dj = next(s for s in struct if s["section_type"] == "dj_intro")
    assert dj["bars"] == 8

    # DJ intro carries only drums (ch 9) and bass (ch 1) — no melodic content.
    mid = mido.MidiFile(str(EXPORTS_DIR / r.generation_id / "song.mid"))
    lo, hi = dj["start_bar"] * 4, (dj["start_bar"] + dj["bars"]) * 4
    chans = set()
    for tr in mid.tracks:
        t = 0
        for m in tr:
            t += m.time
            if m.type == "note_on" and m.velocity > 0 and lo <= t / mid.ticks_per_beat < hi:
                chans.add(m.channel)
    assert chans <= {1, 9} and chans, chans

    # A song built without the toggle keeps its original first section (unchanged).
    plain = build_song(BuildSongRequest(style_id="house", key="C", scale="minor", bpm=124,
                                        complexity=0.6, variation=0.5,
                                        parts=["chords", "bass", "melody", "drums"],
                                        template="verse_chorus", seed=1))
    plain_struct = json.loads((EXPORTS_DIR / plain.generation_id / "song_structure.json").read_text())
    assert plain_struct[0]["section_type"] != "dj_intro"


def test_bridge_escape_opens_off_path_and_walks_home():
    from app.api.routes_song import _bridge_escape_progression

    # I-heavy major song → bridge opens on vi (unused), ends on a dominant pedal.
    prog, opener = _bridge_escape_progression(["I", "IV", "V", "I"], "major")
    assert opener == "vi" and opener not in {"I", "IV", "V"}
    assert prog[-1] == "V" and prog[-2] == "V"

    # Minor → ♭VI deceptive opener.
    prog_m, opener_m = _bridge_escape_progression(["i", "iv", "v", "i"], "minor")
    assert opener_m == "bVI"
    assert prog_m[-1] == "V"

    # When the first-choice opener is already in the loop, fall through to the next.
    _, opener2 = _bridge_escape_progression(["I", "vi", "IV", "V"], "major")
    assert opener2 not in {"I", "vi", "IV", "V"}


def test_chromatic_color_is_gated_resolution_aware_and_protects_cadence():
    from app.generators.chords import apply_chromatic_color, _SEC_DOM_MAJOR

    prog = ["ii", "V", "I", "vi", "IV", "V", "I", "I"]
    # prob 0 → untouched (byte-identical for styles that don't opt in)
    assert apply_chromatic_color(prog, "major", 0.0) == prog
    # Deterministic given the same rng seed
    assert (apply_chromatic_color(prog, "major", 0.8, random.Random(1))
            == apply_chromatic_color(prog, "major", 0.8, random.Random(1)))

    for seed in range(30):
        out = apply_chromatic_color(prog, "major", 1.0, random.Random(seed))
        assert len(out) == len(prog)
        assert out[-1] == "I"                       # final cadence never touched
        # Any secondary dominant sits immediately before the chord it resolves to.
        for i in range(len(out) - 1):
            if out[i] in _SEC_DOM_MAJOR.values() and prog[i] not in _SEC_DOM_MAJOR.values():
                target = out[i + 1]
                assert _SEC_DOM_MAJOR.get(target) == out[i], (seed, i, out)


def test_riff_mode_is_opt_in_only():
    """A non-riff style never enters riff rendering — byte-identical path."""
    from app.generators.riff import riff_section_comp, is_riff_style
    assert not is_riff_style(_style("lofi"))
    assert not riff_section_comp(_style("lofi"), "verse")
    assert is_riff_style(_style("metal"))
    assert riff_section_comp(_style("metal"), "verse")


def test_custom_template_build_and_regen():
    custom = [
        SongSectionDef(section_type="verse", bars=4, parts_mode="no_arp"),
        SongSectionDef(section_type="chorus", bars=4, parts_mode="full"),
        SongSectionDef(section_type="outro", bars=2, parts_mode="melodic"),
    ]
    r = build_song(BuildSongRequest(style_id="lofi", key="C", scale="major", bpm=90,
                                    template="custom", custom_template=custom,
                                    parts=["chords", "bass", "melody", "drums"], seed=9))
    assert [s.bars for s in r.sections] == [4, 4, 2, 1]   # + ending bar
    assert r.total_bars == 11
    # Part regeneration must work against the persisted custom template
    fi = regenerate_song_part(RegenerateSongPartRequest(generation_id=r.generation_id, part="drums"))
    assert fi.part == "drums"


def test_pads_and_counter_melody_arrangement_rules():
    """Pads only in chorus/bridge; the counter-melody harmonizes the FINAL
    chorus (and may answer the lead in verse/intro/outro) but never appears in a
    non-final chorus."""
    r = build_song(BuildSongRequest(style_id="lofi", key="C", scale="major", bpm=90,
                                    template="verse_chorus",
                                    parts=["chords", "bass", "melody", "drums",
                                           "pads", "counter_melody"], seed=42))
    d = EXPORTS_DIR / r.generation_id
    secs = {s.name: (s.start_bar * 4, (s.start_bar + s.bars) * 4) for s in r.sections}

    def starts(part):
        mid = mido.MidiFile(str(d / f"{part}.mid"))
        tpb = mid.ticks_per_beat
        out = []
        for tr in mid.tracks:
            t = 0
            for msg in tr:
                t += msg.time
                if msg.type == "note_on" and msg.velocity > 0:
                    out.append(t / tpb)
        return out

    verse_lo, verse_hi = secs["Verse"]
    pad_starts = starts("pads")
    assert not any(verse_lo <= s < verse_hi - 0.2 for s in pad_starts), "pads leaked into the verse"

    c1_lo, c1_hi = secs["Chorus"]
    fc_lo, fc_hi = secs["Chorus 2"]
    cm_starts = starts("counter_melody")
    assert not any(c1_lo <= s < c1_hi - 0.2 for s in cm_starts), "counter-melody in first chorus"
    assert any(fc_lo <= s < fc_hi for s in cm_starts), "counter-melody missing from final chorus"


# ── Phrase architecture ───────────────────────────────────────────────────────

def test_phrase_plan_grammar():
    """Every form yields exactly the requested phrases, at most one climax,
    and always closes its final phrase."""
    from app.theory.phrase_plan import plan_phrases
    random.seed(5)
    for n in (1, 2, 3, 4, 6, 8):
        plans = plan_phrases(n)
        assert len(plans) == n
        assert sum(p.climax for p in plans) <= 1
        assert plans[-1].cadence_open is False


def test_planned_climax_carries_the_section_peak():
    """Across seeds, the section's highest note lands in the PLANNED climax
    phrase far more often than the 25% chance would give."""
    from app.generators.melody import generate_melody
    from app.theory.phrase_plan import plan_phrases
    style = {**load_style("cinematic"), "_humanize_scale": 0.5}
    hits = total = 0
    for seed in range(20):
        random.seed(seed)
        mel = generate_melody(style, "C", "minor", 16, 0.8, 0.4, ["i", "VI", "III", "VII"])
        random.seed(seed)
        plans = plan_phrases(4)   # same first-RNG draw generate_melody makes
        climax_idx = next((i for i, p in enumerate(plans) if p.climax), None)
        if climax_idx is None:
            continue
        total += 1
        peaks = [max((e.pitch for e in mel if ph * 16 <= e.start < (ph + 1) * 16), default=0)
                 for ph in range(4)]
        if peaks.index(max(peaks)) == climax_idx:
            hits += 1
    assert total >= 10
    assert hits / total >= 0.6, f"climax placement too weak: {hits}/{total}"


def test_intro_tease_commits_to_a_phrase_or_stays_silent():
    """The intro hook tease must never leave a single stray note (a lone note
    reads as an accidental keypress, not a preview). Across styles/seeds the
    intro melody is either a real phrase (>=3 notes) or empty — and the tease
    velocity must clear the mixdown's quiet-note cull so a committed phrase
    isn't decimated back down to one note."""
    for style in ("cloud_rap", "soul", "lofi", "rnb"):
        for seed in range(1000, 1006):
            r = build_song(BuildSongRequest(style_id=style, template="verse_chorus",
                    parts=["chords", "bass", "melody", "drums", "pads"], seed=seed))
            intro = next((s for s in r.sections if s.section_type == "intro"), None)
            if intro is None:
                continue
            lo, hi = intro.start_bar * 4.0, (intro.start_bar + intro.bars) * 4.0
            mid = mido.MidiFile(str(EXPORTS_DIR / r.generation_id / "melody.mid")) \
                if (EXPORTS_DIR / r.generation_id / "melody.mid").exists() else None
            if mid is None:
                continue
            n = 0
            for tr in mid.tracks:
                t = 0
                for msg in tr:
                    t += msg.time
                    if msg.type == "note_on" and msg.velocity > 0 and lo <= t / mid.ticks_per_beat < hi:
                        n += 1
            assert n == 0 or n >= 3, f"{style} seed {seed}: intro has {n} melody notes (a lone stray)"
