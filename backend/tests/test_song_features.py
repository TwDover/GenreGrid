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
                                     regenerate_song_section, build_song_from_melody,
                                     build_song_from_groove)
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


# ── Portable project files (.ggproj) ──────────────────────────────────────────

def _collect_streaming(resp):
    """Drain a StreamingResponse body into bytes (sync test helper)."""
    async def run():
        chunks = []
        async for c in resp.body_iterator:
            chunks.append(c if isinstance(c, (bytes, bytearray)) else c.encode())
        return b"".join(chunks)
    return asyncio.run(run())


def test_project_export_import_round_trip():
    """A .ggproj exported from one song imports into a fresh folder that restores
    the stems byte-for-byte and rehydrates the same song response (roadmap 5.5)."""
    import zipfile
    from fastapi import UploadFile
    from app.api.routes_song import export_project, import_project

    r = _song(seed=71)
    d = EXPORTS_DIR / r.generation_id
    song_bytes = (d / "song.mid").read_bytes()

    data = _collect_streaming(export_project(r.generation_id))
    names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
    assert {"song_meta.json", "song_structure.json", "project.json"} <= names
    assert any(n.endswith(".mid") for n in names)

    imported = asyncio.run(import_project(UploadFile(filename="p.ggproj", file=io.BytesIO(data))))
    assert imported.generation_id != r.generation_id       # fresh id, no collision
    nd = EXPORTS_DIR / imported.generation_id
    assert (nd / "song.mid").read_bytes() == song_bytes     # faithful restore
    assert (nd / "song_meta.json").exists()
    assert imported.style == r.style and imported.total_bars == r.total_bars


def test_import_project_rejects_bad_and_incomplete_archives():
    import zipfile
    import pytest
    from fastapi import UploadFile, HTTPException
    from app.api.routes_song import import_project

    def imp(raw):
        return asyncio.run(import_project(UploadFile(filename="x.ggproj", file=io.BytesIO(raw))))

    with pytest.raises(HTTPException):     # not a zip at all
        imp(b"definitely not a zip")

    buf = io.BytesIO()                     # a zip with a stem but no meta/structure
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("bass.mid", b"MThd-ish")
    with pytest.raises(HTTPException):
        imp(buf.getvalue())


def test_is_safe_project_member_guards_traversal():
    """The import whitelist rejects zip-slip / traversal / stray members."""
    from app.api.routes_song import _is_safe_project_member
    assert _is_safe_project_member("song_meta.json")
    assert _is_safe_project_member("bass.mid")
    assert _is_safe_project_member("sections/verse.mid")
    assert not _is_safe_project_member("../evil.mid")        # traversal
    assert not _is_safe_project_member("/etc/passwd")        # absolute
    assert not _is_safe_project_member("sub/dir/x.mid")      # nested top-level
    assert not _is_safe_project_member("sections/deep/x.mid")  # too deep
    assert not _is_safe_project_member("notes.txt")          # not an allowed type


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
        tempo_automation=0.5, seed=64))
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


# ── Seed from a progression (5.4a) ───────────────────────────────────────────

def test_build_song_with_progression_text_pins_harmony():
    """A typed progression (roman OR chord names) becomes the song's harmony,
    bypassing the style pool; a bad token is rejected with 400."""
    import pytest
    from fastapi import HTTPException

    r = build_song(BuildSongRequest(
        style_id="lofi", key="A", scale="minor", bpm=90, template="minimal",
        parts=["chords", "bass"], seed=71, use_priors=False,
        progression_text="Am F C G"))
    assert r.progression == ["i", "bVI", "bIII", "bVII"]   # A-minor chord names → romans

    r2 = build_song(BuildSongRequest(
        style_id="lofi", key="A", scale="minor", bpm=90, template="minimal",
        parts=["chords", "bass"], seed=71, use_priors=False,
        progression_text="i VI iv v"))
    assert r2.progression == ["i", "VI", "iv", "v"]

    with pytest.raises(HTTPException) as exc:
        build_song(BuildSongRequest(
            style_id="lofi", key="C", scale="major", bpm=90, template="minimal",
            parts=["chords"], seed=71, use_priors=False, progression_text="C Zzz G"))
    assert exc.value.status_code == 400


# ── Seed from a groove (5.4b) ─────────────────────────────────────────────────

def _groove_bytes(kick_beats=(0, 2), snare_beats=(1, 3), bars=4) -> bytes:
    """A synthetic GM drum groove (channel 9): kick/snare on the given beats plus
    steady 8th-note closed hats, as MIDI bytes."""
    mid = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    mid.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    events = []   # (start_beat, pitch)
    for bar in range(bars):
        b0 = bar * 4
        for beat in kick_beats:
            events.append((b0 + beat, 36))
        for beat in snare_beats:
            events.append((b0 + beat, 38))
        for k in range(8):
            events.append((b0 + k * 0.5, 42))
    msgs = []
    for start, pitch in events:
        tick = int(start * 480)
        msgs.append((tick, "note_on", pitch))
        msgs.append((tick + 60, "note_off", pitch))
    msgs.sort(key=lambda x: x[0])
    cur = 0
    for tick, typ, pitch in msgs:
        t.append(mido.Message(typ, channel=9, note=pitch,
                              velocity=100 if typ == "note_on" else 0, time=tick - cur))
        cur = tick
    buf = io.BytesIO()
    mid.save(file=buf)
    return buf.getvalue()


def _build_from_groove(data, **kw):
    from fastapi import UploadFile
    args = dict(style_id="lofi", key="C", scale="minor", bpm=120, time_signature="4/4",
                template="minimal", parts="drums,bass", complexity=0.6, variation=0.4,
                humanize=0.5, use_priors=False, chorus_key_shift=0, final_chorus_lift=0,
                tempo_automation=0.5, progression_text=None, seed=72)
    args.update(kw)
    upload = UploadFile(file=io.BytesIO(data), filename="groove.mid")
    return asyncio.run(build_song_from_groove(file=upload, **args))


def test_build_song_from_groove_end_to_end_and_deterministic():
    data = _groove_bytes()
    r = _build_from_groove(data, seed=72)
    d = EXPORTS_DIR / r.generation_id
    assert (d / "drums.mid").exists() and (d / "song.mid").exists()

    # Same seed + same groove → byte-identical song (seeded determinism).
    r2 = _build_from_groove(data, seed=72)
    assert (EXPORTS_DIR / r2.generation_id / "song.mid").read_bytes() == (d / "song.mid").read_bytes()


def test_groove_drives_the_kick_pattern():
    """A four-on-the-floor upload and a backbeat-only upload produce different
    kicks — proof the mined groove actually reaches the drum generator."""
    import hashlib
    four = _build_from_groove(_groove_bytes(kick_beats=(0, 1, 2, 3)), seed=73)
    two = _build_from_groove(_groove_bytes(kick_beats=(0, 2)), seed=73)
    h_four = hashlib.md5((EXPORTS_DIR / four.generation_id / "drums.mid").read_bytes()).hexdigest()
    h_two = hashlib.md5((EXPORTS_DIR / two.generation_id / "drums.mid").read_bytes()).hexdigest()
    assert h_four != h_two


def test_build_song_from_groove_rejects_non_drum_file():
    import pytest
    from fastapi import HTTPException
    # A pitched melody on channel 0 has no channel-9 drums → 400.
    with pytest.raises(HTTPException) as exc:
        _build_from_groove(_melody_bytes())
    assert exc.value.status_code == 400


def test_groove_can_combine_with_a_typed_progression():
    r = _build_from_groove(_groove_bytes(), seed=74,
                           key="A", scale="minor", progression_text="Am F C G")
    assert r.progression == ["i", "bVI", "bIII", "bVII"]


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


def test_edit_part_drums_rewrites_stem():
    """Editing the drums part must succeed — it skips the melodic CC pass but still
    needs the style loaded for its GM program/track name. A regression guard against
    the UnboundLocalError ('style' unbound) that 500'd every drum-edit/record save."""
    from app.models.schemas import EditPartRequest, EditedNote
    from app.api.routes_song import edit_part

    r = _song(seed=71)
    d = EXPORTS_DIR / r.generation_id
    # A tiny GM drum pattern: kick on 1 and 3, snare on 2 and 4.
    notes = [
        EditedNote(pitch=36, start=0.0, duration=0.25, velocity=110),
        EditedNote(pitch=38, start=1.0, duration=0.25, velocity=95),
        EditedNote(pitch=36, start=2.0, duration=0.25, velocity=110),
        EditedNote(pitch=38, start=3.0, duration=0.25, velocity=95),
    ]
    fi = edit_part(EditPartRequest(generation_id=r.generation_id, part="drums", notes=notes))
    assert fi.part == "drums" and fi.filename == "drums.mid"

    # The stem was rewritten with our hits on the drum channel (9).
    after = _read_stem_notes(d / "drums.mid")
    assert {p for p, _, _, _ in after} == {36, 38}
    song_channels = {msg.channel for tr in mido.MidiFile(str(d / "song.mid")).tracks
                     for msg in tr if msg.type == "note_on"}
    assert 9 in song_channels   # drums re-threaded into the rebuilt song


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


# ── 9.3 — automation lanes (volume/pan curves baked into CC7/CC10) ───────────

def _read_stem_cc(path, control):
    """(start_beats, value) for every control_change of `control` in a stem,
    sorted by start_beats."""
    mid = mido.MidiFile(str(path))
    tpb = mid.ticks_per_beat
    out = []
    for tr in mid.tracks:
        t = 0
        for msg in tr:
            t += msg.time
            if msg.type == "control_change" and msg.control == control:
                out.append((t / tpb, msg.value))
    out.sort(key=lambda e: e[0])
    return out


def test_edit_part_no_automation_stays_byte_identical():
    """Omitting `automation` on an edit must write exactly what edit_part writes
    today: a single default CC10 pan point, no CC7 at all (the byte-identical
    invariant for anyone who never opens the Volume/Pan lane)."""
    from app.models.schemas import EditPartRequest, EditedNote
    from app.api.routes_song import edit_part

    r = _song(seed=81)
    d = EXPORTS_DIR / r.generation_id
    notes = [EditedNote(pitch=64, start=0.0, duration=1.0, velocity=90)]
    edit_part(EditPartRequest(generation_id=r.generation_id, part="melody", notes=notes))

    pan_cc = _read_stem_cc(d / "melody.mid", 10)
    volume_cc = _read_stem_cc(d / "melody.mid", 7)
    assert len(pan_cc) == 1 and pan_cc[0][0] == 0.0
    assert volume_cc == []


def test_edit_part_bakes_volume_and_pan_automation():
    """A drawn volume+pan curve bakes into CC7/CC10 at the exact drawn beats/values,
    replacing the single default CC10 point (not adding to it)."""
    from app.models.schemas import EditPartRequest, EditedNote, PartAutomation, AutomationPoint
    from app.api.routes_song import edit_part

    r = _song(seed=82)
    d = EXPORTS_DIR / r.generation_id
    notes = [EditedNote(pitch=64, start=0.0, duration=1.0, velocity=90)]
    automation = PartAutomation(
        volume=[AutomationPoint(beat=0.0, value=1.0), AutomationPoint(beat=4.0, value=0.5)],
        pan=[AutomationPoint(beat=0.0, value=0.0), AutomationPoint(beat=8.0, value=1.0)],
    )
    edit_part(EditPartRequest(generation_id=r.generation_id, part="melody", notes=notes,
                              automation=automation))

    pan_cc = _read_stem_cc(d / "melody.mid", 10)
    volume_cc = _read_stem_cc(d / "melody.mid", 7)
    assert pan_cc == [(0.0, 0), (8.0, 127)]
    assert volume_cc == [(0.0, 127), (4.0, 64)]


def test_edit_part_drums_can_carry_volume_pan_automation():
    """Drums skip the melodic pan/reverb/sweep CC pass, but every part has its own
    output insert now (Slice 1) — a drawn curve should still bake in for drums."""
    from app.models.schemas import EditPartRequest, EditedNote, PartAutomation, AutomationPoint
    from app.api.routes_song import edit_part

    r = _song(seed=83)
    d = EXPORTS_DIR / r.generation_id
    notes = [EditedNote(pitch=36, start=0.0, duration=0.25, velocity=110)]
    automation = PartAutomation(volume=[AutomationPoint(beat=0.0, value=0.8)])
    edit_part(EditPartRequest(generation_id=r.generation_id, part="drums", notes=notes,
                              automation=automation))

    volume_cc = _read_stem_cc(d / "drums.mid", 7)
    assert volume_cc == [(0.0, 102)]   # round(0.8 * 127)


# ── Note regions (roadmap 9.2 follow-up) — movable/loopable recorded takes ──
# A region is registered via /save-note-region *after* the take's own notes
# already landed in the stem via /edit-part (mirrors the real frontend flow:
# PianoRollEditor captures a take, PartCard.saveEdits() calls editPart() first,
# then saveNoteRegion() once that succeeds). These tests simulate that by
# calling edit_part with the pre-existing notes plus a small synthetic "take"
# at a known absolute position, then registering that take as a region.

def _add_region_via_edit_part(generation_id, part, start_bar, bars, notes_rel):
    """Simulate a recorded take landing in the stem (edit_part) and then being
    registered as a region (save_note_region) — the real two-call frontend
    flow. Returns the created NoteRegionInfo.

    Mirrors PartCard.saveEdits(), which always resends the part's *current*
    automation on every save (`editedAutomation.value ?? midiData.value?.automation`)
    so a plain note edit never silently wipes a previously-drawn curve — read it
    back here too, otherwise this fixture would exercise a save flow the real
    frontend never actually performs.
    """
    from app.models.schemas import EditPartRequest, EditedNote, SaveNoteRegionRequest
    from app.services.mixdown import read_part_automation
    from app.api.routes_song import edit_part, save_note_region

    d = EXPORTS_DIR / generation_id
    part_path = d / f"{part}.mid"
    before = _read_stem_notes(part_path)
    current_automation = read_part_automation(part_path)
    start_beat = start_bar * 4
    abs_notes = [EditedNote(pitch=p, start=start_beat + s, duration=du, velocity=v)
                for p, s, du, v in notes_rel]
    all_notes = [EditedNote(pitch=p, start=s, duration=du, velocity=v) for p, s, du, v in before] + abs_notes
    edit_part(EditPartRequest(generation_id=generation_id, part=part, notes=all_notes,
                              automation=current_automation))

    rel = [EditedNote(pitch=p, start=s, duration=du, velocity=v) for p, s, du, v in notes_rel]
    return save_note_region(SaveNoteRegionRequest(
        generation_id=generation_id, part=part, start_bar=start_bar, bars=bars, notes=rel))


def test_save_note_region_registers_metadata_and_appears_in_song_response():
    from app.api.routes_song import _song_response_from_dir

    r = _song(seed=201)
    d = EXPORTS_DIR / r.generation_id
    region = _add_region_via_edit_part(r.generation_id, "melody", start_bar=2, bars=1,
                                       notes_rel=[(67, 0.0, 1.0, 100), (69, 1.0, 1.0, 100)])

    assert region.part == "melody" and region.start_bar == 2 and region.bars == 1
    assert region.loop_count == 1 and len(region.notes) == 2

    resp = _song_response_from_dir(d)
    assert len(resp.note_regions) == 1
    assert resp.note_regions[0].id == region.id


def test_move_note_region_shifts_its_notes_and_leaves_the_rest_alone():
    from app.models.schemas import MoveNoteRegionRequest
    from app.api.routes_song import move_note_region

    r = _song(seed=202)
    d = EXPORTS_DIR / r.generation_id
    region = _add_region_via_edit_part(r.generation_id, "melody", start_bar=2, bars=1,
                                       notes_rel=[(67, 0.0, 1.0, 100), (69, 1.0, 1.0, 100)])
    # Snapshot the *post-round-trip* note set (write_midi quantizes durations to
    # the nearest tick, so comparing against pre-round-trip values would flag
    # sub-tick float drift as a false "note changed" — capture the baseline
    # after the one round trip every note has already been through.
    before = set(_read_stem_notes(d / "melody.mid"))
    region_notes_old_pos = {(67, 8.0, 1.0, 100), (69, 9.0, 1.0, 100)}
    assert region_notes_old_pos <= before

    resp = move_note_region(region.id, MoveNoteRegionRequest(generation_id=r.generation_id, new_start_bar=5))
    assert resp.file.part == "melody"
    assert resp.regions[0].start_bar == 5

    after = set(_read_stem_notes(d / "melody.mid"))
    # Old absolute position (beats 8/9) is gone; new position (beats 20/21) is present.
    assert region_notes_old_pos.isdisjoint(after)
    assert (67, 20.0, 1.0, 100) in after and (69, 21.0, 1.0, 100) in after
    # Everything else the song already had (i.e. not this region) is untouched, to
    # within one-tick tolerance. Confirmed (via a throwaway script, not specific to
    # this feature) that two plain /edit-part round trips with NO region math at
    # all already drift a handful of notes by exactly one tick (~0.002 beat) —
    # pre-existing note-pairing behavior of the write/read round trip on
    # overlapping-duration notes, not something this feature introduces. A tight
    # decimal-round comparison would flag that pre-existing drift as a false
    # "note changed", so compare with an explicit beat tolerance instead.
    def _approx_in(note, pool):
        p, s, du, v = note
        return any(p == p2 and v == v2 and abs(s - s2) < 0.01 and abs(du - du2) < 0.01
                  for p2, s2, du2, v2 in pool)
    untouched = before - region_notes_old_pos
    assert all(_approx_in(n, after) for n in untouched)


def test_move_note_region_preserves_drawn_automation():
    """Regression guard for the automation-erasure gap found during planning:
    moving/looping a region must not silently wipe a hand-drawn volume/pan
    curve on that part, since the shared rewrite path regenerates CC from
    scratch unless the caller explicitly reads back and re-applies it."""
    from app.models.schemas import EditPartRequest, EditedNote, PartAutomation, AutomationPoint, MoveNoteRegionRequest
    from app.api.routes_song import edit_part, move_note_region

    r = _song(seed=203)
    d = EXPORTS_DIR / r.generation_id
    automation = PartAutomation(
        volume=[AutomationPoint(beat=0.0, value=1.0), AutomationPoint(beat=4.0, value=0.5)],
        pan=[AutomationPoint(beat=0.0, value=0.2), AutomationPoint(beat=8.0, value=0.9)],
    )
    before = _read_stem_notes(d / "melody.mid")
    notes = [EditedNote(pitch=p, start=s, duration=du, velocity=v) for p, s, du, v in before]
    edit_part(EditPartRequest(generation_id=r.generation_id, part="melody", notes=notes, automation=automation))

    region = _add_region_via_edit_part(r.generation_id, "melody", start_bar=6, bars=1,
                                       notes_rel=[(72, 0.0, 1.0, 100)])
    move_note_region(region.id, MoveNoteRegionRequest(generation_id=r.generation_id, new_start_bar=10))

    assert _read_stem_cc(d / "melody.mid", 7) == [(0.0, 127), (4.0, 64)]
    assert _read_stem_cc(d / "melody.mid", 10) == [(0.0, 25), (8.0, 114)]   # round(0.2*127), round(0.9*127)


def test_move_note_region_rejects_out_of_bounds():
    import pytest
    from fastapi import HTTPException
    from app.models.schemas import MoveNoteRegionRequest
    from app.api.routes_song import move_note_region

    r = _song(seed=204)   # compact template: 41 total bars (incl. the 1-bar ending)
    region = _add_region_via_edit_part(r.generation_id, "melody", start_bar=2, bars=1,
                                       notes_rel=[(67, 0.0, 1.0, 100)])
    with pytest.raises(HTTPException) as exc:
        move_note_region(region.id, MoveNoteRegionRequest(generation_id=r.generation_id, new_start_bar=100))
    assert exc.value.status_code == 400


def test_set_note_region_loop_repeats_the_recorded_content():
    from app.models.schemas import SetNoteRegionLoopRequest
    from app.api.routes_song import set_note_region_loop

    r = _song(seed=205)
    d = EXPORTS_DIR / r.generation_id
    region = _add_region_via_edit_part(r.generation_id, "melody", start_bar=2, bars=1,
                                       notes_rel=[(67, 0.0, 1.0, 100)])

    resp = set_note_region_loop(region.id, SetNoteRegionLoopRequest(generation_id=r.generation_id, loop_count=3))
    assert resp.regions[0].loop_count == 3

    after = set(_read_stem_notes(d / "melody.mid"))
    # Repeats at start_bar 2, 3, 4 (bars=1 apart) → beats 8, 12, 16.
    assert (67, 8.0, 1.0, 100) in after
    assert (67, 12.0, 1.0, 100) in after
    assert (67, 16.0, 1.0, 100) in after


def test_delete_note_region_removes_notes_and_metadata():
    from app.api.routes_song import delete_note_region, _song_response_from_dir

    r = _song(seed=206)
    d = EXPORTS_DIR / r.generation_id
    region = _add_region_via_edit_part(r.generation_id, "melody", start_bar=2, bars=1,
                                       notes_rel=[(67, 0.0, 1.0, 100), (69, 1.0, 1.0, 100)])

    resp = delete_note_region(r.generation_id, region.id)
    assert resp.regions == []

    after = set(_read_stem_notes(d / "melody.mid"))
    assert (67, 8.0, 1.0, 100) not in after and (69, 9.0, 1.0, 100) not in after
    assert _song_response_from_dir(d).note_regions == []


def test_save_note_region_overlap_replaces_existing_region():
    from app.api.routes_song import _song_response_from_dir

    r = _song(seed=207)
    d = EXPORTS_DIR / r.generation_id
    _add_region_via_edit_part(r.generation_id, "melody", start_bar=2, bars=2,
                              notes_rel=[(67, 0.0, 1.0, 100)])
    # A re-recorded take over an overlapping span (bars 3-4 overlaps bars 2-3).
    second = _add_region_via_edit_part(r.generation_id, "melody", start_bar=3, bars=2,
                                       notes_rel=[(70, 0.0, 1.0, 100)])

    regions = _song_response_from_dir(d).note_regions
    assert len(regions) == 1 and regions[0].id == second.id

    after = set(_read_stem_notes(d / "melody.mid"))
    assert (67, 8.0, 1.0, 100) not in after    # the replaced take's note is gone
    assert (70, 12.0, 1.0, 100) in after       # the new take's note is present


def test_regenerate_song_part_prunes_the_stale_region_on_that_part():
    from app.models.schemas import RegenerateSongPartRequest
    from app.api.routes_song import regenerate_song_part, _song_response_from_dir

    r = _song(seed=208)
    d = EXPORTS_DIR / r.generation_id
    _add_region_via_edit_part(r.generation_id, "melody", start_bar=2, bars=1,
                              notes_rel=[(67, 0.0, 1.0, 100)])
    assert len(_song_response_from_dir(d).note_regions) == 1

    regenerate_song_part(RegenerateSongPartRequest(generation_id=r.generation_id, part="melody"))
    assert _song_response_from_dir(d).note_regions == []


def test_rearrange_song_sections_prunes_all_regions():
    from app.models.schemas import RearrangeSongSectionsRequest
    from app.api.routes_song import rearrange_song_sections, _song_response_from_dir

    r = _rearrange_song(seed=209)
    d = EXPORTS_DIR / r.generation_id
    _add_region_via_edit_part(r.generation_id, "melody", start_bar=1, bars=1,
                              notes_rel=[(67, 0.0, 1.0, 100)])
    assert len(_song_response_from_dir(d).note_regions) == 1

    real = [s for s in r.sections if s.section_type != "ending"]
    defs = [_def_from_result(s, i) for i, s in enumerate(reversed(real))]
    rearrange_song_sections(RearrangeSongSectionsRequest(generation_id=r.generation_id, sections=defs))
    assert _song_response_from_dir(d).note_regions == []


def test_song_tempo_map_intensity():
    """The tempo-automation knob scales the chorus push, pre-chorus lean and
    ending ritardando: 0 = flat, 0.5 = the classic subtle default, 1 = double."""
    from app.core.arrangement import _song_tempo_map
    bpm = 120.0
    sections = [
        {"start_bar": 0,  "bars": 4, "section_type": "verse"},
        {"start_bar": 4,  "bars": 2, "section_type": "pre_chorus"},
        {"start_bar": 6,  "bars": 4, "section_type": "chorus"},
        {"start_bar": 10, "bars": 4, "section_type": "verse"},   # drops back to base
    ]

    # Off → a single flat tempo point, no movement anywhere.
    assert _song_tempo_map(sections, bpm, ending_bars=1, intensity=0.0) == [(0.0, 120.0)]

    # Subtle (default 0.5) → the historical values, byte-for-byte.
    subtle = {round(b, 4) for _, b in _song_tempo_map(sections, bpm, ending_bars=1, intensity=0.5)}
    assert round(120 * 1.006, 4) in subtle   # pre-chorus lean
    assert round(120 * 1.012, 4) in subtle   # chorus push
    assert round(120 * 0.76, 4) in subtle    # deepest ritardando step
    assert 120.0 in subtle                    # base + drop-back to base after chorus

    # Expressive (1.0) → the same gestures at double the deviation.
    expr = {round(b, 4) for _, b in _song_tempo_map(sections, bpm, ending_bars=1, intensity=1.0)}
    assert round(120 * 1.024, 4) in expr      # chorus push doubled
    assert round(120 * 0.52, 4) in expr       # deepest ritardando doubled (1 - 0.48)


# ── 9.2 — section timeline rearrange (reorder/insert/delete/duplicate/resize) ─

def _rearrange_song(seed=91):
    """A 3-section custom-template song to rearrange."""
    custom = [
        SongSectionDef(section_type="verse", bars=4, parts_mode="no_arp"),
        SongSectionDef(section_type="chorus", bars=4, parts_mode="full", chorus_key=True),
        SongSectionDef(section_type="bridge", bars=4, parts_mode="full", bridge_key=True),
    ]
    return build_song(BuildSongRequest(style_id="lofi", key="C", scale="major", bpm=110,
                                       template="custom", custom_template=custom,
                                       parts=["chords", "bass", "melody", "drums"],
                                       seed=seed, use_priors=False))


def _def_from_result(sec, source_index):
    from app.models.schemas import RearrangeSectionDef
    return RearrangeSectionDef(section_type=sec.section_type, bars=sec.bars, name=sec.name,
                               parts_mode=sec.parts_mode, chorus_key=sec.chorus_key,
                               bridge_key=sec.bridge_key, style_id=sec.style_id,
                               source_index=source_index)


def test_rearrange_reorders_sections_and_updates_layout():
    import json
    from app.models.schemas import RearrangeSongSectionsRequest
    from app.api.routes_song import rearrange_song_sections

    r = _rearrange_song(seed=101)
    d = EXPORTS_DIR / r.generation_id
    real = [s for s in r.sections if s.section_type != "ending"]
    assert [s.section_type for s in real] == ["verse", "chorus", "bridge"]

    reversed_defs = [_def_from_result(s, i) for s, i in zip(reversed(real), [2, 1, 0])]
    result = rearrange_song_sections(RearrangeSongSectionsRequest(
        generation_id=r.generation_id, sections=reversed_defs))

    new_real = [s for s in result.sections if s.section_type != "ending"]
    assert [s.section_type for s in new_real] == ["bridge", "chorus", "verse"]
    assert [s.start_bar for s in new_real] == [0, 4, 8]
    assert result.total_bars == r.total_bars

    meta = json.loads((d / "song_meta.json").read_text())
    assert [sd["section_type"] for sd in meta["custom_template"]] == ["bridge", "chorus", "verse"]
    structure = json.loads((d / "song_structure.json").read_text())
    assert [s["section_type"] for s in structure if s["section_type"] != "ending"] == ["bridge", "chorus", "verse"]


def test_rearrange_round_trip_is_byte_identical():
    """Reversing and reversing back reuses every section's original seed, so the
    stems should reproduce the pre-rearrange bytes exactly (roadmap 9.2's core
    'content stability via source_index' contract)."""
    import hashlib
    from app.models.schemas import RearrangeSongSectionsRequest
    from app.api.routes_song import rearrange_song_sections

    r = _rearrange_song(seed=102)
    d = EXPORTS_DIR / r.generation_id

    def hashes():
        return {p: hashlib.md5((d / f"{p}.mid").read_bytes()).hexdigest()
                for p in ("chords", "bass", "melody", "drums")}

    before = hashes()
    real = [s for s in r.sections if s.section_type != "ending"]

    reversed_defs = [_def_from_result(s, i) for s, i in zip(reversed(real), [2, 1, 0])]
    result1 = rearrange_song_sections(RearrangeSongSectionsRequest(
        generation_id=r.generation_id, sections=reversed_defs))
    assert hashes() != before   # actually changed order → different bytes

    # Reverse again: back to the original verse/chorus/bridge order, each
    # section still reusing its ORIGINAL build seed via source_index.
    real1 = [s for s in result1.sections if s.section_type != "ending"]
    back_defs = [_def_from_result(s, i) for s, i in zip(reversed(real1), [2, 1, 0])]
    rearrange_song_sections(RearrangeSongSectionsRequest(
        generation_id=r.generation_id, sections=back_defs))

    assert hashes() == before   # byte-identical round trip


def test_rearrange_insert_generates_fresh_content():
    from app.models.schemas import RearrangeSongSectionsRequest, RearrangeSectionDef
    from app.api.routes_song import rearrange_song_sections

    r = _rearrange_song(seed=103)
    real = [s for s in r.sections if s.section_type != "ending"]
    defs = [_def_from_result(s, i) for i, s in enumerate(real)]
    defs.append(RearrangeSectionDef(section_type="verse", bars=4, parts_mode="no_arp"))

    result = rearrange_song_sections(RearrangeSongSectionsRequest(
        generation_id=r.generation_id, sections=defs))
    new_real = [s for s in result.sections if s.section_type != "ending"]
    assert len(new_real) == 4
    assert result.total_bars == r.total_bars + 4
    inserted = new_real[-1]
    assert inserted.section_type == "verse"
    assert inserted.quality is not None   # went through the quality-search path


def test_rearrange_delete_reduces_bar_count():
    from app.models.schemas import RearrangeSongSectionsRequest
    from app.api.routes_song import rearrange_song_sections

    r = _rearrange_song(seed=104)
    real = [s for s in r.sections if s.section_type != "ending"]
    defs = [_def_from_result(s, i) for i, s in enumerate(real)][:-1]   # drop the bridge

    result = rearrange_song_sections(RearrangeSongSectionsRequest(
        generation_id=r.generation_id, sections=defs))
    new_real = [s for s in result.sections if s.section_type != "ending"]
    assert [s.section_type for s in new_real] == ["verse", "chorus"]
    assert result.total_bars == r.total_bars - 4


def test_rearrange_duplicate_reuses_seed_for_both_copies():
    from app.models.schemas import RearrangeSongSectionsRequest
    from app.api.routes_song import rearrange_song_sections

    r = _rearrange_song(seed=105)
    real = [s for s in r.sections if s.section_type != "ending"]
    defs = [_def_from_result(s, i) for i, s in enumerate(real)]
    defs.insert(1, _def_from_result(real[0], 0))   # duplicate the verse right after itself

    result = rearrange_song_sections(RearrangeSongSectionsRequest(
        generation_id=r.generation_id, sections=defs))
    new_real = [s for s in result.sections if s.section_type != "ending"]
    assert [s.section_type for s in new_real] == ["verse", "verse", "chorus", "bridge"]
    assert result.total_bars == r.total_bars + 4


def test_rearrange_resize_changes_bars_same_seed():
    from app.models.schemas import RearrangeSongSectionsRequest
    from app.api.routes_song import rearrange_song_sections

    r = _rearrange_song(seed=106)
    real = [s for s in r.sections if s.section_type != "ending"]
    defs = [_def_from_result(s, i) for i, s in enumerate(real)]
    defs[1] = defs[1].model_copy(update={"bars": 8})   # double the chorus

    result = rearrange_song_sections(RearrangeSongSectionsRequest(
        generation_id=r.generation_id, sections=defs))
    new_real = [s for s in result.sections if s.section_type != "ending"]
    assert new_real[1].bars == 8
    assert result.total_bars == r.total_bars + 4


def test_rearrange_blocked_when_parts_locked():
    from fastapi import HTTPException
    import pytest
    from app.models.schemas import RearrangeSongSectionsRequest
    from app.api.routes_song import rearrange_song_sections

    r = _rearrange_song(seed=107)
    d = EXPORTS_DIR / r.generation_id
    meta_before = (d / "song_meta.json").read_text()
    versions_before = list((d / "versions").glob("*")) if (d / "versions").exists() else []

    real = [s for s in r.sections if s.section_type != "ending"]
    defs = [_def_from_result(s, i) for i, s in enumerate(reversed(real))]
    with pytest.raises(HTTPException) as exc:
        rearrange_song_sections(RearrangeSongSectionsRequest(
            generation_id=r.generation_id, sections=defs, locked_parts=["melody"]))
    assert exc.value.status_code == 400

    # Nothing mutated: no snapshot taken, meta untouched.
    versions_after = list((d / "versions").glob("*")) if (d / "versions").exists() else []
    assert len(versions_after) == len(versions_before)
    assert (d / "song_meta.json").read_text() == meta_before


def test_rearrange_is_undoable_via_history():
    import json
    from app.models.schemas import RearrangeSongSectionsRequest
    from app.api.routes_song import rearrange_song_sections, list_song_versions, restore_song_version
    from app.models.schemas import RestoreSongVersionRequest

    r = _rearrange_song(seed=108)
    d = EXPORTS_DIR / r.generation_id
    original_structure = json.loads((d / "song_structure.json").read_text())

    real = [s for s in r.sections if s.section_type != "ending"]
    defs = [_def_from_result(s, i) for i, s in enumerate(reversed(real))]
    rearrange_song_sections(RearrangeSongSectionsRequest(
        generation_id=r.generation_id, sections=defs))
    assert json.loads((d / "song_structure.json").read_text()) != original_structure

    versions = list_song_versions(r.generation_id)
    assert versions   # the pre-rearrange snapshot
    restore_song_version(RestoreSongVersionRequest(generation_id=r.generation_id, version_id=versions[0]["id"]))

    restored_structure = json.loads((d / "song_structure.json").read_text())
    restored_meta = json.loads((d / "song_meta.json").read_text())
    assert [s["section_type"] for s in restored_structure] == [s["section_type"] for s in original_structure]
    assert [sd["section_type"] for sd in restored_meta["custom_template"]] == ["verse", "chorus", "bridge"]


def test_generate_song_sections_mixed_fixed_and_search_seeds():
    """Unit-level check of the per-section fixed-vs-search seeding (roadmap 9.2
    §0.1): a None entry inside an otherwise-fixed list still runs the
    quality-gated search for just that section."""
    from app.services.song_builder import _generate_song_sections
    from app.services.style_loader import load_style

    r = _rearrange_song(seed=109)
    style = load_style("lofi")
    d = EXPORTS_DIR / r.generation_id
    import json
    meta = json.loads((d / "song_meta.json").read_text())
    seeds = meta["section_seeds"]
    assert len(seeds) == 3

    song_req = BuildSongRequest.model_construct(
        style_id="lofi", key="C", scale="major", bpm=110, time_signature="4/4",
        complexity=0.6, variation=0.4, humanize=0.5, dynamics=0.5,
        parts=["chords", "bass", "melody", "drums"], template="custom", use_priors=False,
        seed=meta["base_seed"], chorus_key_shift=meta["chorus_key_shift"],
    )
    mixed_seeds = [seeds[0], None, seeds[2]]
    _events, section_results, _total, out_seeds, _prog = _generate_song_sections(
        song_req, style, 110, meta["base_seed"], meta["chorus_key_shift"],
        False, False, 0.0, fixed_section_seeds=mixed_seeds,
        custom_template=meta["custom_template"],
        user_progression=meta.get("song_progression"),
    )
    assert out_seeds[0] == seeds[0]
    assert out_seeds[2] == seeds[2]
    # The searched section still gets a quality score; the two replayed
    # sections keep whatever quality they scored on the original build.
    assert section_results[1]["quality"] is not None
