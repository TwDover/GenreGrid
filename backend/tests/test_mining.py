# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""End-to-end test of the corpus-mining pipeline on a synthetic corpus.

We synthesise MIDI songs with a *known* key and chord progression, mine them,
and assert the pipeline recovers that ground truth — then show a progression can
be sampled back out and fed to the generator vocabulary.
"""
import random

from app.mining.corpus import mine_directory
from app.mining.analysis import detect_key
from app.mining.midi_io import read_song
from app.services.midi_writer import NoteEvent, write_midi
from app.services.priors import sample_progression, best_loop, describe
from app.theory.chords import roman_to_chord
from app.theory.notes import note_name_to_midi


# Ground truth: A minor, a i–VI–III–VII loop, with a simple scale-tone melody.
KEY = "A"
MODE = "minor"
PROGRESSION = ["i", "VI", "III", "VII"]
_MELODY_DEGREES = [0, 2, 3, 5, 7, 5, 3, 2]   # A-minor scale steps over each bar


def _write_song(path, seed: int) -> None:
    rng = random.Random(seed)
    events: list[NoteEvent] = []
    tonic = note_name_to_midi(KEY, 4)
    scale = [0, 2, 3, 5, 7, 8, 10]
    bars = 8
    for bar in range(bars):
        roman = PROGRESSION[bar % len(PROGRESSION)]
        beat0 = bar * 4.0
        # Chords on channel 0 (whole-bar triad)
        for p in roman_to_chord(roman, KEY, MODE, octave=4):
            events.append(NoteEvent(p, beat0, 3.8, 70, channel=0))
        # Bass root on channel 1
        root = roman_to_chord(roman, KEY, MODE, octave=3)[0]
        events.append(NoteEvent(root, beat0, 3.8, 80, channel=1))
        # Melody on channel 2 — four quarter notes from the scale, high register
        for q in range(4):
            deg = _MELODY_DEGREES[(bar * 4 + q) % len(_MELODY_DEGREES)]
            pitch = tonic + 12 + scale[deg % len(scale)] + (12 if rng.random() < 0.1 else 0)
            events.append(NoteEvent(pitch, beat0 + q, 0.9, 75, channel=2))
    write_midi(events, path, bpm=100)


def _build_corpus(tmp_path, n=6):
    d = tmp_path / "corpus"
    d.mkdir()
    for i in range(n):
        _write_song(d / f"song_{i}.mid", seed=i)
    return d


def test_key_detection_recovers_a_minor(tmp_path):
    p = tmp_path / "one.mid"
    _write_song(p, seed=1)
    key, mode = detect_key(read_song(p))
    assert key == "A"
    assert mode == "minor"


def test_mining_recovers_progression_and_melody(tmp_path):
    corpus = _build_corpus(tmp_path, n=6)
    prior = mine_directory(corpus, "testgenre")

    # Files were all used and detected as minor
    assert prior["files_used"] == 6
    assert prior["keys"]["minor"] >= prior["keys"]["major"]

    # Harmony: the tonic and the progression's chords show up as top tokens
    uni = prior["harmony"]["unigram"]
    assert uni.get("i", 0) > 0, f"expected tonic 'i' in {uni}"
    # The four progression roots should dominate the vocabulary
    for tok in PROGRESSION:
        assert tok in uni, f"{tok} missing from mined chords {uni}"

    # The exact 4-bar loop should be recovered as the most common loop
    loop = best_loop(prior)
    assert loop == PROGRESSION, f"recovered loop {loop} != {PROGRESSION}"

    # Melody stats were collected
    mel = prior["melody"]
    assert mel["note_events"] > 0
    assert sum(mel["intervals"].values()) > 0
    assert sum(mel["durations"].values()) > 0

    # describe() runs without error and mentions the genre
    assert "testgenre" in describe(prior)


def _write_major_pop(path, seed: int) -> None:
    """A major-key I–V–vi–IV song with stepwise melody (for the wiring test)."""
    rng = random.Random(seed)
    ev: list[NoteEvent] = []
    tonic = note_name_to_midi("C", 4)
    sc = [0, 2, 4, 5, 7, 9, 11]
    prog = [["I", "V", "vi", "IV"], ["vi", "IV", "I", "V"]][seed % 2]
    for bar in range(8):
        r = prog[bar % 4]
        b0 = bar * 4.0
        for p in roman_to_chord(r, "C", "major", octave=4):
            ev.append(NoteEvent(p, b0, 3.8, 66, 0))
        ev.append(NoteEvent(roman_to_chord(r, "C", "major", octave=3)[0], b0, 3.8, 80, 1))
        idx = rng.randrange(7)
        for q in range(4):
            idx = max(0, min(6, idx + rng.choice([-1, -1, 0, 1, 1, 2, -2])))
            ev.append(NoteEvent(tonic + 12 + sc[idx], b0 + q, 0.9, 74, 2))
    write_midi(ev, path, bpm=120)


def test_priors_change_live_generation(tmp_path, monkeypatch):
    """A mined prior should steer the live generate() progression, and use_priors=False
    should fall back to the style template — the A/B path end to end."""
    import app.services.priors as priors
    from app.mining.corpus import mine_directory
    from app.models.schemas import GenerateRequest
    from app.api.routes_generate import generate

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for i in range(24):
        _write_major_pop(corpus / f"s{i}.mid", seed=i)

    prior = mine_directory(corpus, "house")
    priors_dir = tmp_path / "priors"
    priors_dir.mkdir()
    (priors_dir / "house.json").write_text(__import__("json").dumps(prior))
    monkeypatch.setattr(priors, "_PRIORS_DIR", priors_dir)
    priors._cache.clear()

    base = dict(style_id="house", key="C", scale="major", bpm=120, bars=8,
                complexity=0.6, variation=0.5,
                parts=["chords", "bass", "melody", "drums"], mode="arrangement", seed=42)
    on = generate(GenerateRequest(**base, use_priors=True))
    off = generate(GenerateRequest(**base, use_priors=False))

    # The learned progression (major-key) should appear when priors are on, and it
    # should differ from the template-driven run.
    assert on.progression == ["I", "V", "vi", "IV"]
    assert on.progression != off.progression
    priors._cache.clear()


def test_sample_progression_uses_generator_vocabulary(tmp_path):
    corpus = _build_corpus(tmp_path, n=6)
    prior = mine_directory(corpus, "testgenre")

    prog = sample_progression(prior, length=4, seed=7)
    assert prog is not None and len(prog) == 4
    # Every sampled token must be a legal roman the generator can voice
    for tok in prog:
        pitches = roman_to_chord(tok, KEY, MODE, octave=4)
        assert len(pitches) >= 3
