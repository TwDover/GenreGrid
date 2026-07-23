# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Song Builder feature tests: MIDI markers, version history, style blending,
and the melody-import pipeline (key detection, chord derivation, hook placement)."""
import asyncio
import io

import mido

from app.core.config import EXPORTS_DIR
from app.models.schemas import (BuildSongRequest, SongSectionDef,
                                RegenerateSongPartRequest, RestoreSongVersionRequest)
from app.api.routes_song import (build_song, regenerate_song_part,
                                     list_song_versions, restore_song_version,
                                     regenerate_song_section, build_song_from_melody)
from app.services.midi_writer import NoteEvent, write_midi
from app.services.melody_import import parse_melody_midi, detect_key, derive_progression, fit_melody_to_bars


def _song(seed=61, **kw):
    args = dict(style_id="lofi", key="C", scale="major", bpm=90, template="compact",
                parts=["chords", "bass", "melody", "drums"], seed=seed, use_priors=False)
    args.update(kw)
    return build_song(BuildSongRequest(**args))


def test_section_reroll_keeps_locked_parts_byte_identical():
    """A section re-roll regenerates only the unlocked parts; locked stems stay
    byte-for-byte, and the response omits them (roadmap-2 item 8)."""
    import hashlib
    from app.models.schemas import RegenerateSongSectionRequest

    r = _song(seed=77)
    d = EXPORTS_DIR / r.generation_id

    def h(part):
        return hashlib.md5((d / f"{part}.mid").read_bytes()).hexdigest()

    before = {p: h(p) for p in ("chords", "bass", "melody", "drums")}
    files = regenerate_song_section(RegenerateSongSectionRequest(
        generation_id=r.generation_id, section_index=1, locked_parts=["melody", "bass"]))
    after = {p: h(p) for p in ("chords", "bass", "melody", "drums")}

    assert before["melody"] == after["melody"]   # locked → untouched
    assert before["bass"] == after["bass"]
    assert before["chords"] != after["chords"]   # unlocked → re-rolled
    returned = {f.part for f in files}
    assert "melody" not in returned and "bass" not in returned
    assert "chords" in returned


def test_roll_and_keep_song_part_candidates():
    """Rolling candidates writes distinct throwaway stems without touching the
    live stem; keeping one promotes it and clears the rest (roadmap-2 item 7)."""
    import hashlib
    from app.api.routes_song import roll_song_part_candidates, keep_song_part_candidate
    from app.models.schemas import RollSongPartRequest, KeepSongPartCandidateRequest

    r = _song(seed=88)
    d = EXPORTS_DIR / r.generation_id

    def h(name):
        return hashlib.md5((d / name).read_bytes()).hexdigest()

    live_before = h("melody.mid")
    cands = roll_song_part_candidates(RollSongPartRequest(
        generation_id=r.generation_id, part="melody", count=3))
    assert len(cands) == 3
    assert h("melody.mid") == live_before          # live stem untouched by rolling
    hashes = [h(c.filename) for c in cands]
    assert len(set(hashes)) == 3                    # candidates differ from each other

    keep_song_part_candidate(KeepSongPartCandidateRequest(
        generation_id=r.generation_id, part="melody", index=2))
    assert h("melody.mid") == hashes[2]             # kept candidate is now live
    assert not list(d.glob("melody.cand*.mid"))     # candidates cleared
    assert (d / "melody.prev").exists()             # one-level undo preserved


def test_rebuild_song_progression_edits_harmony_and_validates():
    """Editing the progression rebuilds the song (new id) with the chosen chords;
    a typo is rejected before any regeneration (roadmap-2 item 6)."""
    import pytest
    from fastapi import HTTPException
    from app.api.routes_song import rebuild_song_progression
    from app.models.schemas import RebuildSongProgressionRequest

    r = _song(seed=91)
    out = rebuild_song_progression(RebuildSongProgressionRequest(
        generation_id=r.generation_id, progression=["i", "iv", "v", "i"]))
    assert out.progression == ["i", "iv", "v", "i"]
    assert out.generation_id != r.generation_id     # a fresh song; the original stays on disk

    with pytest.raises(HTTPException) as exc:
        rebuild_song_progression(RebuildSongProgressionRequest(
            generation_id=r.generation_id, progression=["i", "zzz", "v", "i"]))
    assert exc.value.status_code == 400


# ── MIDI markers + key signature ─────────────────────────────────────────────

def test_song_mid_has_section_markers_and_key_signature():
    r = _song()
    mid = mido.MidiFile(str(EXPORTS_DIR / r.generation_id / "song.mid"))
    metas = [msg for tr in mid.tracks for msg in tr if msg.is_meta]
    marker_texts = [m.text for m in metas if m.type == "marker"]
    assert "Intro" in marker_texts and "Chorus" in marker_texts and "End" in marker_texts
    keys = [m.key for m in metas if m.type == "key_signature"]
    assert keys == ["C"]


# ── Version history ───────────────────────────────────────────────────────────

def test_version_history_snapshot_and_restore():
    r = _song(seed=62)
    d = EXPORTS_DIR / r.generation_id
    melody_v1 = (d / "melody.mid").read_bytes()

    # No versions until the first mutation
    assert list_song_versions(r.generation_id) == []

    regenerate_song_part(RegenerateSongPartRequest(generation_id=r.generation_id, part="melody"))
    assert (d / "melody.mid").read_bytes() != melody_v1

    versions = list_song_versions(r.generation_id)
    assert len(versions) == 1

    files = restore_song_version(RestoreSongVersionRequest(
        generation_id=r.generation_id, version_id=versions[0]["id"]))
    assert any(f.part == "melody" for f in files)
    assert (d / "melody.mid").read_bytes() == melody_v1   # back to the original
    # The restore snapshotted the pre-restore state, so it's undoable too
    assert len(list_song_versions(r.generation_id)) == 2


# ── Per-section style ─────────────────────────────────────────────────────────

def test_custom_template_per_section_style():
    custom = [
        SongSectionDef(section_type="verse", bars=4, parts_mode="no_arp"),
        SongSectionDef(section_type="chorus", bars=4, parts_mode="full",
                       style_id="house"),   # chorus generates in a different style
        SongSectionDef(section_type="outro", bars=2, parts_mode="melodic"),
    ]
    r = build_song(BuildSongRequest(style_id="lofi", key="C", scale="major", bpm=110,
                                    template="custom", custom_template=custom,
                                    parts=["chords", "bass", "melody", "drums"],
                                    seed=63, use_priors=False))
    assert r.total_bars == 11
    # Regeneration replays the section style without error
    fi = regenerate_song_part(RegenerateSongPartRequest(generation_id=r.generation_id, part="drums"))
    assert fi.part == "drums"


# ── Melody import pipeline ────────────────────────────────────────────────────

def _melody_bytes(key_root=60, minor=False) -> bytes:
    """A clear 4-bar diatonic melody as MIDI bytes (C major or C minor)."""
    sc = [0, 2, 3, 5, 7, 8, 10] if minor else [0, 2, 4, 5, 7, 9, 11]
    ev = []
    seqs = [[0, 2, 4, 2], [0, 3, 5, 3], [4, 2, 1, 0], [0, 1, 2, 0]]
    for bar, steps in enumerate(seqs):
        for q, s in enumerate(steps):
            ev.append(NoteEvent(key_root + sc[s], bar * 4 + q, 0.9, 90, 0))
    import tempfile
    import os
    fd, path = tempfile.mkstemp(suffix=".mid")
    os.close(fd)
    write_midi(ev, path, bpm=100)
    data = open(path, "rb").read()
    os.unlink(path)
    return data


def test_detect_key_major_and_minor():
    mel, bpm = parse_melody_midi(_melody_bytes(minor=False))
    assert bpm and abs(bpm - 100) < 1
    assert detect_key(mel) == ("C", "major")
    mel_m, _ = parse_melody_midi(_melody_bytes(minor=True))
    assert detect_key(mel_m) == ("C", "minor")


def test_derive_progression_is_diatonic_and_covers_melody():
    mel, _ = parse_melody_midi(_melody_bytes())
    prog = derive_progression(mel, "C", "major")
    assert len(prog) == 4
    assert prog[0] == "I"   # bar 1 sits on the tonic
    assert all(p in ("I", "ii", "iii", "IV", "V", "vi") for p in prog)


def test_fit_melody_loops_to_fill_bars():
    mel, _ = parse_melody_midi(_melody_bytes())   # 4 bars
    fitted = fit_melody_to_bars(mel, 8)
    assert max(n.start for n in fitted) >= 16     # looped into bars 5-8
    assert all(n.start + n.duration <= 32.01 for n in fitted)


def test_build_song_from_melody_end_to_end():
    from fastapi import UploadFile
    data = _melody_bytes()
    upload = UploadFile(file=io.BytesIO(data), filename="hook.mid")
    r = asyncio.run(build_song_from_melody(
        file=upload, style_id="lofi", template="compact",
        parts="chords,bass,melody,drums", complexity=0.6, variation=0.4,
        humanize=0.5, use_priors=False, chorus_key_shift=0, final_chorus_lift=0,
        seed=64))
    assert r.key.startswith("C major")
    d = EXPORTS_DIR / r.generation_id

    # The chorus melody IS the uploaded hook (same relative onsets and pitches)
    chorus = next(s for s in r.sections if s.section_type == "chorus")
    mid = mido.MidiFile(str(d / "melody.mid"))
    tpb = mid.ticks_per_beat
    notes = []
    for tr in mid.tracks:
        t = 0
        for msg in tr:
            t += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                notes.append((t / tpb, msg.note))
    lo, hi = chorus.start_bar * 4, (chorus.start_bar + chorus.bars) * 4
    chorus_notes = {(round((t - lo) % 16, 1), p) for t, p in notes if lo <= t < hi}
    hook, _ = parse_melody_midi(data)
    hook_set = {(round(n.start, 1), n.pitch) for n in hook}
    matched = sum(1 for ev in hook_set if ev in chorus_notes)
    assert matched / len(hook_set) >= 0.9, "chorus should carry the uploaded hook"

    # Regenerating a part replays the hook context without error
    fi = regenerate_song_part(RegenerateSongPartRequest(generation_id=r.generation_id, part="drums"))
    assert fi.part == "drums"


# ── Note editing (/edit-part) ────────────────────────────────────────────────

def _read_stem_notes(path):
    """(pitch, start_beats, duration_beats, velocity) for every note in a stem,
    sorted by (start, pitch)."""
    mid = mido.MidiFile(str(path))
    tpb = mid.ticks_per_beat
    notes = []
    for tr in mid.tracks:
        t = 0
        open_notes: dict[tuple[int, int], list] = {}
        for msg in tr:
            t += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                open_notes.setdefault((msg.channel, msg.note), []).append((t, msg.velocity))
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                stack = open_notes.get((msg.channel, msg.note))
                if stack:
                    start, vel = stack.pop(0)
                    notes.append((msg.note, start / tpb, (t - start) / tpb, vel))
    notes.sort(key=lambda n: (n[1], n[0]))
    return notes


def test_edit_part_rewrites_stem_and_snapshots():
    from app.models.schemas import EditPartRequest, EditedNote
    from app.api.routes_song import edit_part

    r = _song(seed=66)
    d = EXPORTS_DIR / r.generation_id
    before = _read_stem_notes(d / "melody.mid")
    assert len(before) >= 3
    song_v1 = (d / "song.mid").read_bytes()
    versions_before = len(list_song_versions(r.generation_id))

    # Delete the first note, transpose the (new) first remaining note up 2.
    deleted = before[0]
    kept = before[1:]
    target = kept[0]
    notes = [EditedNote(pitch=(p + 2 if i == 0 else p), start=s,
                        duration=max(dur, 0.01), velocity=v)
             for i, (p, s, dur, v) in enumerate(kept)]
    fi = edit_part(EditPartRequest(generation_id=r.generation_id, part="melody", notes=notes))
    assert fi.part == "melody" and fi.filename == "melody.mid"

    def _has(notes_list, pitch, start, tol=0.01):
        return any(p == pitch and abs(s - start) < tol for p, s, _, _ in notes_list)

    after = _read_stem_notes(d / "melody.mid")
    assert len(after) == len(before) - 1
    assert not _has(after, deleted[0], deleted[1])   # deletion landed
    assert _has(after, target[0] + 2, target[1])     # transposition landed
    assert not _has(after, target[0], target[1])     # old pitch is gone

    # song.mid was rebuilt from the edited stems. Identify the melody track by
    # MIDI channel (2) — track NAMES are instrument display labels now
    # ("Rhodes EP (melody)"), never a stable identifier.
    assert (d / "song.mid").read_bytes() != song_v1
    song_channels = {msg.channel for tr in mido.MidiFile(str(d / "song.mid")).tracks
                     for msg in tr if msg.type == "note_on"}
    assert 2 in song_channels

    # The pre-edit state was snapshotted, so the edit is restorable
    assert len(list_song_versions(r.generation_id)) == versions_before + 1


def test_edit_part_404_on_missing_song_or_stem():
    import pytest
    from fastapi import HTTPException
    from app.models.schemas import EditPartRequest, EditedNote
    from app.api.routes_song import edit_part

    note = [EditedNote(pitch=60, start=0.0, duration=1.0, velocity=90)]
    with pytest.raises(HTTPException) as exc:
        edit_part(EditPartRequest(generation_id="nosuchsong", part="melody", notes=note))
    assert exc.value.status_code == 404

    r = _song(seed=67, parts=["chords", "bass", "drums"])   # no melody stem
    with pytest.raises(HTTPException) as exc:
        edit_part(EditPartRequest(generation_id=r.generation_id, part="melody", notes=note))
    assert exc.value.status_code == 404
