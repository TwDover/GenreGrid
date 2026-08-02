# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Song Builder endpoints and orchestration: templates -> sections -> stems,
plus per-part/per-section regeneration, version history, and melody import.

Split out of routes_generate.py; the loop/arrangement generation core
(_run_attempt and friends) stays there and is imported here.
"""
import logging
import random
import re
import secrets
import shutil
import uuid
import json as _json_module

from fastapi import APIRouter, HTTPException, UploadFile, Form
from fastapi import File as FastAPIFile

from app.models.schemas import (FileInfo, BuildSongRequest, BuildSongResponse,
                                SongSectionResult, RegenerateSongPartRequest,
                                RegenerateSongSectionRequest, RestoreSongVersionRequest,
                                SetPartGainRequest, EditPartRequest, SongSectionDef,
                                RollSongPartRequest, SongPartCandidate, KeepSongPartCandidateRequest,
                                RebuildSongProgressionRequest, RearrangeSongSectionsRequest)
from app.services.style_loader import load_style
from app.services.progression_import import parse_progression, ROMAN_TOKEN_RE
from app.services.midi_writer import (NoteEvent, write_midi, rebuild_combined_from_parts, mido_key_signature)
from app.core.config import EXPORTS_DIR
from app.core.meter import parse_meter
from app.core.arrangement import (
    _SONG_TEMPLATES, _song_tempo_map,
)
from app.services.mixdown import (
    _PART_CHANNELS, part_midi_meta,
    _generate_part_cc, _generate_melody_expression_cc, _apply_automation_cc,
    _generate_808_pitch_bends, _drop_quiet, _scale_velocity, generate_build_sweeps, generate_section_crescendo,
)
from app.api.routes_generate import _SAFE_PATH
from app.services.generation import (
    _blend_styles,
)

from app.services.song_builder import (
    _generate_song_sections,
    _section_markers, _write_song_output,
)

router = APIRouter()
logger = logging.getLogger(__name__)
@router.post("/build-song", response_model=BuildSongResponse)
def build_song(req: BuildSongRequest):
    """Generate a full song by stitching independently-generated sections.

    A free-typed `progression_text` (roman numerals or chord names) is parsed into
    the `progression_override` seam so the song is built on the user's harmony,
    bypassing the style's progression pool (mirrors the melody-import derivation).
    """
    if req.progression_text and req.progression_text.strip():
        try:
            req.progression_override = parse_progression(req.progression_text, req.key, req.scale)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return _do_build_song(req)


# Single-token roman validator, shared with progression_import.
_ROMAN_TOKEN_RE = ROMAN_TOKEN_RE


@router.post("/rebuild-song-progression", response_model=BuildSongResponse)
def rebuild_song_progression(req: RebuildSongProgressionRequest):
    """Rebuild a song with a user-edited progression (roadmap-2 item 6).

    Everything else — style, key, seed, template, section layout — is replayed
    from the original build, so only the harmony changes. Produces a new song
    (the original stays on disk); the edited progression is validated against the
    song's key before anything is regenerated."""
    output_dir = EXPORTS_DIR / req.generation_id
    meta_path = output_dir / "song_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Song not found or too old to edit")
    meta = _json_module.loads(meta_path.read_text())

    key, scale = meta.get("key", "C"), meta.get("scale", "minor")
    prog = [r.strip() for r in req.progression if r.strip()]
    if len(prog) < 2:
        raise HTTPException(status_code=400, detail="A progression needs at least two chords")
    # Validate each token is a real roman numeral (optional accidental + I–VII in
    # either case + an optional chord-quality suffix) — roman_to_chord silently
    # defaults unknown tokens to the tonic, so a shape check is what actually rejects typos.
    for roman in prog:
        if not _ROMAN_TOKEN_RE.match(roman):
            raise HTTPException(status_code=400, detail=f"'{roman}' isn't a valid roman numeral")

    custom = meta.get("custom_template")
    song_req = BuildSongRequest(
        style_id=meta["style_id"], key=key, scale=scale, bpm=meta["bpm"],
        time_signature=meta.get("time_signature", "4/4"),
        complexity=meta["complexity"], variation=meta["variation"],
        dynamics=meta.get("dynamics", 0.5), humanize=meta["humanize"],
        parts=meta["parts"], template=meta.get("template", "verse_chorus"),
        seed=meta["base_seed"], use_priors=meta["use_priors"],
        chorus_key_shift=meta.get("chorus_key_shift"),
        bridge_key_shift=meta.get("bridge_key_shift"),
        final_chorus_lift=meta.get("final_chorus_lift"),
        custom_template=[SongSectionDef(**sd) for sd in custom] if custom else None,
        blend_style_id=meta.get("blend_style_id"),
        blend_amount=meta.get("blend_amount", 0.5),
        dj_edit=meta.get("dj_edit", False),
        progression_override=prog,
    )
    # Preserve an imported hook melody (melody-import songs) while overriding harmony.
    return _do_build_song(song_req, hook_melody=_hook_from_meta(meta))


def _do_build_song(req: BuildSongRequest, user_progression: list[str] | None = None,
                   hook_melody: list[NoteEvent] | None = None,
                   groove_override: dict | None = None) -> BuildSongResponse:
    """Shared song-build core. `user_progression`/`hook_melody` come from the
    melody-import endpoint: the song is built around the user's uploaded idea.
    `groove_override` — a mined groove (derived drum fields + feel) from the
    groove-import endpoint; overlaid onto the style so the drums play the user's
    uploaded feel."""
    try:
        style = load_style(req.style_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = max(bpm_min, min(bpm_max, req.bpm))

    gen_id = str(uuid.uuid4())[:8]
    output_dir = EXPORTS_DIR / gen_id
    output_dir.mkdir(parents=True, exist_ok=True)

    programs, track_names = part_midi_meta(style)
    secondary_dominants = style.get("secondary_dominants", False)
    tritone_sub = style.get("tritone_substitution", False)
    groove_push = style.get("groove_push", 0.0)
    # User-controlled chorus modulation overrides the style default when provided.
    chorus_key_shift = req.chorus_key_shift if req.chorus_key_shift is not None else style.get("chorus_key_shift", 0)
    # Bridges default to a lift to the subdominant (a common bridge-modulation target)
    # unless the style or request overrides it — unlike chorus_key_shift, which
    # defaults to no shift, bridges benefit from contrast out of the box.
    bridge_key_shift = req.bridge_key_shift if req.bridge_key_shift is not None else style.get("bridge_key_shift", 5)
    # Gear change on the LAST chorus only — classic pop move, on by default (+1).
    final_chorus_lift = req.final_chorus_lift if req.final_chorus_lift is not None else style.get("final_chorus_lift", 1)
    custom_template = ([sd.model_dump() for sd in req.custom_template]
                       if req.custom_template else None)
    style = _blend_styles(style, getattr(req, "blend_style_id", None), getattr(req, "blend_amount", 0.5))
    style = {**style, "_humanize_scale": req.humanize}

    # Overlay an uploaded groove's mined drum fields + feel onto the style. The
    # "__uploaded__" sentinel names a groove with no file on disk, so the
    # generator's own _overlay_groove step (priors.groove_fields_for) finds
    # nothing and leaves this injection intact.
    if groove_override:
        derived = groove_override.get("derived") or {}
        drums = {**style.get("drums", {}), **derived}
        if groove_override.get("fills"):
            drums["fills"] = groove_override["fills"]
        style = {**style, "drums": drums, "groove": "__uploaded__"}
        if groove_override.get("feel"):
            style["feel"] = groove_override["feel"]

    base_seed = req.seed if req.seed is not None else random.randint(0, 2**31 - 1)

    song_events, section_results, total_bars, section_seeds, song_progression = _generate_song_sections(
        req, style, bpm, base_seed, chorus_key_shift,
        secondary_dominants, tritone_sub, groove_push,
        bridge_key_shift=bridge_key_shift,
        final_chorus_lift=final_chorus_lift,
        custom_template=custom_template,
        user_progression=user_progression or getattr(req, "progression_override", None),
        hook_melody=hook_melody,
    )

    # Persist the params needed to regenerate a single part later.
    import json as _jmeta
    (output_dir / "song_meta.json").write_text(_jmeta.dumps({
        "style_id": req.style_id, "key": req.key, "scale": req.scale,
        "time_signature": getattr(req, "time_signature", "4/4"),
        "bpm": bpm, "complexity": req.complexity, "variation": req.variation,
        "dynamics": req.dynamics, "tempo_automation": req.tempo_automation,
        "humanize": req.humanize, "parts": list(req.parts), "template": req.template,
        "use_priors": req.use_priors, "chorus_key_shift": chorus_key_shift,
        "bridge_key_shift": bridge_key_shift, "base_seed": base_seed,
        "final_chorus_lift": final_chorus_lift, "custom_template": custom_template,
        "blend_style_id": getattr(req, "blend_style_id", None),
        "blend_amount": getattr(req, "blend_amount", 0.5),
        "dj_edit": getattr(req, "dj_edit", False),
        "user_progression": user_progression,
        # The resolved song progression, pinned so section re-rolls reproduce it
        # and the UI can show/lock it (roadmap-2 item 6).
        "song_progression": song_progression,
        "hook_melody": ([[e.pitch, round(e.start, 4), round(e.duration, 4), e.velocity, e.channel]
                         for e in hook_melody] if hook_melody else None),
        "section_seeds": section_seeds,
    }))

    files = _write_song_output(song_events, output_dir, gen_id, bpm, style, programs,
                               list(req.parts), total_bars, section_results,
                               key=req.key, scale=req.scale,
                               meter=parse_meter(getattr(req, "time_signature", None)),
                               tempo_automation=req.tempo_automation)

    import json as _jsong
    (output_dir / "song_structure.json").write_text(_jsong.dumps(section_results, indent=2))

    return BuildSongResponse(
        generation_id=gen_id,
        style=req.style_id,
        files=files,
        seed=base_seed,
        template=req.template,
        total_bars=total_bars,
        sections=[SongSectionResult(**s) for s in section_results],
        bpm=bpm,
        key=f"{req.key} {req.scale}",
        progression=song_progression,
    )


_ALL_SONG_PARTS = frozenset({"chords", "bass", "melody", "drums", "arpeggio", "pads", "counter_melody"})


@router.post("/regenerate-song-part", response_model=FileInfo)
def regenerate_song_part(req: RegenerateSongPartRequest):
    """Re-roll a single part of a built song — or add a part that wasn't built.

    Reruns the song's section loop with only the target part's seed salted, so
    harmony and every other part stay identical; writes the new stem and rebuilds
    song.mid from the on-disk stems. When the requested part wasn't in the
    original build (e.g. the user forgot to tick pads), it is generated fresh
    against the song's persisted seeds and added to the song's part list.
    """
    output_dir = EXPORTS_DIR / req.generation_id
    meta_path = output_dir / "song_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Song not found or too old to regenerate")
    meta = _json_module.loads(meta_path.read_text())
    is_new_part = req.part not in meta.get("parts", [])
    if is_new_part:
        if req.part not in _ALL_SONG_PARTS:
            raise HTTPException(status_code=400, detail=f"Unknown part '{req.part}'")
        if req.part == "counter_melody" and "melody" not in meta.get("parts", []):
            raise HTTPException(status_code=400,
                                detail="counter_melody needs the melody part in the song")

    try:
        style = load_style(meta["style_id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = max(bpm_min, min(bpm_max, meta["bpm"]))
    secondary_dominants = style.get("secondary_dominants", False)
    tritone_sub = style.get("tritone_substitution", False)
    groove_push = style.get("groove_push", 0.0)
    style = _blend_styles(style, meta.get("blend_style_id"), meta.get("blend_amount", 0.5))
    style = {**style, "_humanize_scale": meta["humanize"]}
    programs, track_names = part_midi_meta(style)

    _snapshot_song(output_dir)   # version history: state before this mutation

    gen_parts = list(meta["parts"]) + ([req.part] if is_new_part else [])
    song_req = BuildSongRequest.model_construct(
        style_id=meta["style_id"], key=meta["key"], scale=meta["scale"], bpm=meta["bpm"],
        time_signature=meta.get("time_signature", "4/4"),
        complexity=meta["complexity"], variation=meta["variation"], humanize=meta["humanize"],
        dynamics=meta.get("dynamics", 0.5),
        parts=gen_parts, template=meta["template"], use_priors=meta["use_priors"],
        seed=meta["base_seed"], chorus_key_shift=meta["chorus_key_shift"],
        dj_edit=meta.get("dj_edit", False),   # keep the DJ bookends so section seeds still line up
    )

    salt = secrets.randbelow(2 ** 31) or 1   # non-zero so the part actually changes
    song_events, _sections, total_bars, _seeds, _prog = _generate_song_sections(
        song_req, style, bpm, meta["base_seed"], meta["chorus_key_shift"],
        secondary_dominants, tritone_sub, groove_push,
        regen_part=req.part, regen_salt=salt,
        bridge_key_shift=meta.get("bridge_key_shift", 0),
        fixed_section_seeds=meta.get("section_seeds"),
        final_chorus_lift=meta.get("final_chorus_lift", 0),
        custom_template=meta.get("custom_template"),
        # Pin the persisted progression so a part re-roll targets the same harmony.
        user_progression=meta.get("song_progression") or meta.get("user_progression"),
        hook_melody=_hook_from_meta(meta),
    )

    evts = song_events.get(req.part) or []
    if not evts:
        hint = ""
        if req.part == "counter_melody":
            hint = " — the counter-melody plays only in the final chorus, and this template has no chorus"
        elif req.part == "pads":
            hint = " — pads play only in chorus and bridge sections, and this template has neither"
        raise HTTPException(status_code=400 if is_new_part else 500,
                            detail=f"No events generated for {req.part}{hint}")

    _sid = style.get("id", "")
    part_cc = None
    if req.part != "drums":
        channel = _PART_CHANNELS.get(req.part, 0)
        part_cc = _generate_part_cc(req.part, total_bars, channel, style=style)
        if req.part == "melody":
            part_cc = part_cc + _generate_melody_expression_cc(evts, channel)
        # A re-rolled stem keeps its pre-chorus sweeps/crescendo (build_song adds
        # these in _write_song_output, which this single-stem path bypasses)
        for automation in (generate_build_sweeps(_sections, [req.part]),
                           generate_section_crescendo(_sections, [req.part])):
            part_cc = part_cc + automation.get(req.part, [])
    part_pb = None
    if req.part == "bass" and style.get("bass", {}).get("bass_style") == "808":
        part_pb = _generate_808_pitch_bends(evts, _PART_CHANNELS.get("bass", 1))

    tempo_map = _song_tempo_map(_sections, bpm, ending_bars=1, meter=parse_meter(meta.get("time_signature", "4/4")), intensity=meta.get("tempo_automation", 0.5))
    scaled = _drop_quiet(_scale_velocity(evts, req.part, _sid))
    fname = f"{req.part}.mid"
    part_path = output_dir / fname
    # Back up the current stem (one level of undo). The ".prev" name has no .mid
    # extension so rebuild_combined_from_parts won't fold it into the song.
    if part_path.exists():
        shutil.copy(part_path, output_dir / f"{req.part}.prev")
    write_midi(scaled, part_path, bpm=bpm, program=programs.get(req.part),
               cc_events=part_cc, pb_events=part_pb, tempo_events=tempo_map,
               track_name=track_names.get(req.part))

    # Rebuild song.mid from all stems on disk (new part + untouched others).
    rebuild_combined_from_parts(output_dir, bpm, combined_name="song.mid", meter=parse_meter(meta.get("time_signature", "4/4")), tempo_events=tempo_map,
                                markers=_section_markers(_sections, meta.get("key", "C"), parse_meter(meta.get("time_signature", "4/4"))),
                                key_signature=mido_key_signature(meta.get("key", "C"), meta.get("scale", "minor")),
                                track_names=track_names)

    # An added part becomes a first-class member of the song so later
    # regenerations and undos treat it like any originally-built stem.
    if is_new_part:
        meta["parts"] = gen_parts
        meta_path.write_text(_json_module.dumps(meta))

    return FileInfo(part=req.part, filename=fname, url=f"/exports/{req.generation_id}/{fname}")


def _render_song_part_stem(output_dir, meta: dict, style: dict, part: str, salt: int,
                           programs: dict, track_names: dict, bpm: int, out_name: str) -> bool:
    """Render one variation of a song part (salted) and write it to `out_name`,
    WITHOUT touching the live stem or song.mid. Used to roll compare-and-keep
    candidates. Returns False when the part produced no notes."""
    secondary_dominants = style.get("secondary_dominants", False)
    tritone_sub = style.get("tritone_substitution", False)
    groove_push = style.get("groove_push", 0.0)

    song_req = BuildSongRequest.model_construct(
        style_id=meta["style_id"], key=meta["key"], scale=meta["scale"], bpm=meta["bpm"],
        time_signature=meta.get("time_signature", "4/4"),
        complexity=meta["complexity"], variation=meta["variation"], humanize=meta["humanize"],
        dynamics=meta.get("dynamics", 0.5),
        parts=meta["parts"], template=meta["template"], use_priors=meta["use_priors"],
        seed=meta["base_seed"], chorus_key_shift=meta["chorus_key_shift"],
        dj_edit=meta.get("dj_edit", False),
    )
    song_events, _sections, total_bars, _seeds, _prog = _generate_song_sections(
        song_req, style, bpm, meta["base_seed"], meta["chorus_key_shift"],
        secondary_dominants, tritone_sub, groove_push,
        regen_part=part, regen_salt=salt,
        bridge_key_shift=meta.get("bridge_key_shift", 0),
        fixed_section_seeds=meta.get("section_seeds"),
        final_chorus_lift=meta.get("final_chorus_lift", 0),
        custom_template=meta.get("custom_template"),
        user_progression=meta.get("song_progression") or meta.get("user_progression"),
        hook_melody=_hook_from_meta(meta),
    )
    evts = song_events.get(part) or []
    if not evts:
        return False

    _sid = style.get("id", "")
    part_cc = None
    if part != "drums":
        channel = _PART_CHANNELS.get(part, 0)
        part_cc = _generate_part_cc(part, total_bars, channel, style=style)
        if part == "melody":
            part_cc = part_cc + _generate_melody_expression_cc(evts, channel)
        for automation in (generate_build_sweeps(_sections, [part]),
                           generate_section_crescendo(_sections, [part])):
            part_cc = part_cc + automation.get(part, [])
    part_pb = None
    if part == "bass" and style.get("bass", {}).get("bass_style") == "808":
        part_pb = _generate_808_pitch_bends(evts, _PART_CHANNELS.get("bass", 1))

    tempo_map = _song_tempo_map(_sections, bpm, ending_bars=1, meter=parse_meter(meta.get("time_signature", "4/4")), intensity=meta.get("tempo_automation", 0.5))
    scaled = _drop_quiet(_scale_velocity(evts, part, _sid))
    write_midi(scaled, output_dir / out_name, bpm=bpm, program=programs.get(part),
               cc_events=part_cc, pb_events=part_pb, tempo_events=tempo_map,
               track_name=track_names.get(part))
    return True


def _clear_part_candidates(output_dir, part: str) -> None:
    for f in output_dir.glob(f"{part}.cand*.mid"):
        f.unlink(missing_ok=True)


@router.post("/roll-song-part-candidates", response_model=list[SongPartCandidate])
def roll_song_part_candidates(req: RollSongPartRequest):
    """Roll several candidate variations of one song part so the user can compare
    and keep the best (roadmap-2 item 7). Candidates are written to separate
    `{part}.candN.mid` files; the live stem and song.mid are left untouched until
    the user commits one via /keep-song-part-candidate."""
    output_dir = EXPORTS_DIR / req.generation_id
    meta_path = output_dir / "song_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Song not found or too old to re-roll")
    meta = _json_module.loads(meta_path.read_text())
    if req.part not in meta.get("parts", []):
        raise HTTPException(status_code=400, detail=f"'{req.part}' is not a part of this song")

    try:
        style = load_style(meta["style_id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = max(bpm_min, min(bpm_max, meta["bpm"]))
    style = _blend_styles(style, meta.get("blend_style_id"), meta.get("blend_amount", 0.5))
    style = {**style, "_humanize_scale": meta["humanize"]}
    programs, track_names = part_midi_meta(style)

    _clear_part_candidates(output_dir, req.part)
    candidates: list[SongPartCandidate] = []
    # Deterministic per-generation salts so the same song always rolls the same
    # candidate set (reproducible), while each candidate differs from the others.
    for i in range(req.count):
        salt = (secrets.randbelow(2 ** 31) or 1)
        out_name = f"{req.part}.cand{i}.mid"
        if _render_song_part_stem(output_dir, meta, style, req.part, salt,
                                  programs, track_names, bpm, out_name):
            candidates.append(SongPartCandidate(
                index=i, filename=out_name,
                url=f"/exports/{req.generation_id}/{out_name}"))
    if not candidates:
        raise HTTPException(status_code=500, detail=f"No candidates generated for {req.part}")
    return candidates


@router.post("/keep-song-part-candidate", response_model=FileInfo)
def keep_song_part_candidate(req: KeepSongPartCandidateRequest):
    """Commit a rolled candidate as the part's live stem: snapshot for history,
    promote the chosen candidate, rebuild song.mid, and clear the candidates."""
    output_dir = EXPORTS_DIR / req.generation_id
    meta_path = output_dir / "song_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Song not found")
    meta = _json_module.loads(meta_path.read_text())
    cand_path = output_dir / f"{req.part}.cand{req.index}.mid"
    if not cand_path.exists():
        raise HTTPException(status_code=404, detail="That candidate is no longer available — re-roll to try again")

    try:
        style = load_style(meta["style_id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = max(bpm_min, min(bpm_max, meta["bpm"]))
    style = _blend_styles(style, meta.get("blend_style_id"), meta.get("blend_amount", 0.5))
    style = {**style, "_humanize_scale": meta["humanize"]}
    _, track_names = part_midi_meta(style)

    _snapshot_song(output_dir)   # version history: state before this mutation
    live = output_dir / f"{req.part}.mid"
    if live.exists():
        shutil.copy(live, output_dir / f"{req.part}.prev")   # one-level undo
    shutil.copy(cand_path, live)
    _clear_part_candidates(output_dir, req.part)

    layout = _template_section_results(
        meta.get("template", "verse_chorus"), meta.get("key", "C"),
        custom=meta.get("custom_template"))
    rebuild_combined_from_parts(
        output_dir, bpm, combined_name="song.mid", meter=parse_meter(meta.get("time_signature", "4/4")),
        tempo_events=_song_tempo_map(layout, bpm, ending_bars=1, meter=parse_meter(meta.get("time_signature", "4/4")), intensity=meta.get("tempo_automation", 0.5)),
        markers=_section_markers(layout, meta.get("key", "C"), parse_meter(meta.get("time_signature", "4/4"))),
        key_signature=mido_key_signature(meta.get("key", "C"), meta.get("scale", "minor")),
        track_names=track_names)
    return FileInfo(part=req.part, filename=f"{req.part}.mid",
                    url=f"/exports/{req.generation_id}/{req.part}.mid")


def _template_section_results(template_name: str, key: str = "C",
                              custom: list[dict] | None = None) -> list[dict]:
    """Section layout (start_bar/bars/type) for a template, including the ending
    bar — enough to rebuild the tempo map without regenerating any music."""
    template = custom or _SONG_TEMPLATES.get(template_name, _SONG_TEMPLATES["verse_chorus"])
    out, sb = [], 0
    for sd in template:
        bars = sd.get("bars", 8)
        out.append({"name": sd.get("name") or sd["section_type"], "section_type": sd["section_type"],
                    "bars": bars, "start_bar": sb, "key": key})
        sb += bars
    out.append({"name": "End", "section_type": "ending", "bars": 1, "start_bar": sb, "key": key})
    return out


def _hook_from_meta(meta: dict) -> list[NoteEvent] | None:
    """Rebuild the imported hook melody persisted in song_meta.json."""
    raw = meta.get("hook_melody")
    if not raw:
        return None
    return [NoteEvent(int(p), float(s), float(d), int(v), int(ch)) for p, s, d, v, ch in raw]


@router.post("/build-song-from-melody", response_model=BuildSongResponse)
async def build_song_from_melody(
    file: UploadFile = FastAPIFile(...),
    style_id: str = Form(...),
    template: str = Form("verse_chorus"),
    parts: str = Form("chords,bass,melody,drums,pads"),
    complexity: float = Form(0.6),
    variation: float = Form(0.4),
    humanize: float = Form(0.5),
    use_priors: bool = Form(False),
    chorus_key_shift: int = Form(0),
    final_chorus_lift: int = Form(1),
    tempo_automation: float = Form(0.5),
    seed: int | None = Form(None),
):
    """Build a full song around an uploaded melody.

    The melody's key is detected (Krumhansl-Schmuckler), a supporting chord
    progression is derived bar by bar, and the melody becomes the song's chorus
    hook — repeats, the intro tease, the counter-melody, and every section's
    motif development all grow out of the user's idea.
    """
    from app.services.melody_import import parse_melody_midi, detect_key, derive_progression

    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(status_code=400, detail="MIDI file too large (5 MB max)")
    try:
        melody, file_bpm = parse_melody_midi(data)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse that file as MIDI")
    if len(melody) < 4:
        raise HTTPException(status_code=400, detail="No usable melody found in the file (need at least 4 notes)")

    key, scale = detect_key(melody)
    progression = derive_progression(melody, key, scale)

    try:
        style = load_style(style_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = int(max(bpm_min, min(bpm_max, file_bpm or 120)))

    req = BuildSongRequest(
        style_id=style_id, key=key, scale=scale, bpm=bpm,
        complexity=complexity, variation=variation, humanize=humanize,
        parts=[p.strip() for p in parts.split(",") if p.strip()],
        template=template, seed=seed, use_priors=use_priors,
        chorus_key_shift=chorus_key_shift, final_chorus_lift=final_chorus_lift,
        tempo_automation=tempo_automation,
    )
    return _do_build_song(req, user_progression=progression, hook_melody=melody)


def _mine_uploaded_groove(data: bytes) -> dict | None:
    """Mine a finalized groove (derived drum fields + feel + fills) from an
    uploaded drum-MIDI file, reusing the corpus miner (app.mining.drums). Returns
    None if the file has no usable channel-10 drum groove."""
    import os
    import tempfile
    from app.mining.midi_io import read_song
    from app.mining.drums import (empty_groove, analyze_drum_song,
                                   analyze_fill_song, finalize_groove)

    tmp = tempfile.NamedTemporaryFile(suffix=".mid", delete=False)
    try:
        tmp.write(data)
        tmp.close()
        song = read_song(tmp.name)
    finally:
        os.unlink(tmp.name)

    groove = empty_groove("__uploaded__")
    if not analyze_drum_song(song, groove):
        return None
    analyze_fill_song(song, groove)          # best-effort: mine one fill if present
    return finalize_groove(groove)


@router.post("/build-song-from-groove", response_model=BuildSongResponse)
async def build_song_from_groove(
    file: UploadFile = FastAPIFile(...),
    style_id: str = Form(...),
    key: str = Form("C"),
    scale: str = Form("minor"),
    bpm: int = Form(120),
    time_signature: str = Form("4/4"),
    template: str = Form("verse_chorus"),
    parts: str = Form("chords,bass,melody,drums,pads"),
    complexity: float = Form(0.6),
    variation: float = Form(0.4),
    humanize: float = Form(0.5),
    use_priors: bool = Form(False),
    chorus_key_shift: int = Form(0),
    final_chorus_lift: int = Form(1),
    tempo_automation: float = Form(0.5),
    progression_text: str | None = Form(None),
    seed: int | None = Form(None),
):
    """Build a full song whose drums play an uploaded groove's feel.

    The groove .mid is mined (kick/snare pattern, hat placement, swing, and the
    per-class microtiming/velocity feel) with the same analyzer the corpus miner
    uses, then overlaid onto the chosen style's drums. Harmony/melody are still
    generated by the style (optionally seeded by a typed progression).
    """
    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(status_code=400, detail="MIDI file too large (5 MB max)")
    try:
        groove = _mine_uploaded_groove(data)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse that file as MIDI")
    if not groove:
        raise HTTPException(status_code=400, detail="No usable drum groove found (need channel-10 / GM drums with at least 16 hits)")

    try:
        load_style(style_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    req = BuildSongRequest(
        style_id=style_id, key=key, scale=scale, bpm=bpm, time_signature=time_signature,
        complexity=complexity, variation=variation, humanize=humanize,
        parts=[p.strip() for p in parts.split(",") if p.strip()],
        template=template, seed=seed, use_priors=use_priors,
        chorus_key_shift=chorus_key_shift, final_chorus_lift=final_chorus_lift,
        tempo_automation=tempo_automation,
    )
    if progression_text and progression_text.strip():
        try:
            req.progression_override = parse_progression(progression_text, key, scale)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return _do_build_song(req, groove_override=groove)


def _rescale_stem_velocities(path, factor: float) -> None:
    """Rewrite a stem .mid scaling note-on velocities by `factor` (clamped 1-127),
    preserving CC, pitch bends, tempo map, markers, and program changes."""
    import mido
    mid = mido.MidiFile(str(path))
    for track in mid.tracks:
        for msg in track:
            if msg.type == "note_on" and msg.velocity > 0:
                msg.velocity = max(1, min(127, round(msg.velocity * factor)))
    mid.save(str(path))


@router.post("/set-part-gain", response_model=FileInfo)
def set_part_gain(req: SetPartGainRequest):
    """In-app mixer: set a part's gain relative to how it was generated (1.0).

    The stem's velocities are rescaled on disk (so preview, drag-to-DAW, and
    exports all reflect it) and the setting persists in song_meta so it shows
    correctly after a reload. Gains are absolute, not cumulative — setting 1.0
    restores the generated balance exactly (modulo integer rounding).
    """
    output_dir = EXPORTS_DIR / req.generation_id
    meta_path = output_dir / "song_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Song not found")
    part_path = output_dir / f"{req.part}.mid"
    if not part_path.exists():
        raise HTTPException(status_code=404, detail=f"No {req.part} stem in this song")

    meta = _json_module.loads(meta_path.read_text())
    mixer = meta.get("mixer") or {}
    old_gain = float(mixer.get(req.part, 1.0))
    factor = req.gain / old_gain if old_gain > 1e-6 else req.gain
    if abs(factor - 1.0) > 1e-6:
        _rescale_stem_velocities(part_path, factor)

    mixer[req.part] = req.gain
    meta["mixer"] = mixer
    meta_path.write_text(_json_module.dumps(meta))

    bpm = meta.get("bpm", 120)
    layout = _template_section_results(meta.get("template", "verse_chorus"), meta.get("key", "C"),
                                       custom=meta.get("custom_template"))
    try:
        _, _track_names = part_midi_meta(load_style(meta.get("style_id", "")))
    except Exception:
        logger.warning("Could not load style %r for track names — using defaults",
                       meta.get("style_id", ""), exc_info=True)
        _track_names = {}
    rebuild_combined_from_parts(output_dir, bpm, combined_name="song.mid", meter=parse_meter(meta.get("time_signature", "4/4")),
                                tempo_events=_song_tempo_map(layout, bpm, ending_bars=1, meter=parse_meter(meta.get("time_signature", "4/4")), intensity=meta.get("tempo_automation", 0.5)),
                                markers=_section_markers(layout, meta.get("key", "C"), parse_meter(meta.get("time_signature", "4/4"))),
                                key_signature=mido_key_signature(meta.get("key", "C"), meta.get("scale", "minor")),
                                track_names=_track_names)
    return FileInfo(part=req.part, filename=f"{req.part}.mid",
                    url=f"/exports/{req.generation_id}/{req.part}.mid")


@router.post("/edit-part", response_model=FileInfo)
def edit_part(req: EditPartRequest):
    """Light note editing: replace a song stem's notes with a hand-edited list.

    The stem is rewritten on disk (same tempo map, program, and part CC as the
    sibling endpoints) and song.mid is rebuilt from the stems, so preview,
    drag-to-DAW, and exports all reflect the edit. The pre-edit state is
    snapshotted first, so an edit is restorable from the History picker.
    """
    if not _SAFE_PATH.match(req.generation_id):
        raise HTTPException(status_code=400, detail="Invalid generation id")
    if req.part not in _ALL_SONG_PARTS:
        raise HTTPException(status_code=400, detail=f"Unknown part '{req.part}'")
    output_dir = EXPORTS_DIR / req.generation_id
    meta_path = output_dir / "song_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Song not found")
    part_path = output_dir / f"{req.part}.mid"
    if not part_path.exists():
        raise HTTPException(status_code=404, detail=f"No {req.part} stem in this song")

    meta = _json_module.loads(meta_path.read_text())
    _snapshot_song(output_dir)   # version history: state before this mutation

    bpm = meta.get("bpm", 120)
    layout = _template_section_results(meta.get("template", "verse_chorus"), meta.get("key", "C"),
                                       custom=meta.get("custom_template"))
    tempo_map = _song_tempo_map(layout, bpm, ending_bars=1, meter=parse_meter(meta.get("time_signature", "4/4")), intensity=meta.get("tempo_automation", 0.5))
    total_bars = sum(s["bars"] for s in layout)

    channel = 9 if req.part == "drums" else _PART_CHANNELS.get(req.part, 0)
    events = [NoteEvent(n.pitch, n.start, n.duration, n.velocity, channel) for n in req.notes]

    # Same CC treatment as regenerate_song_part — pan/reverb per part, plus
    # expression swells re-derived from the edited melody line. The style is loaded
    # unconditionally: drums skip the CC pass but still need it for the GM program +
    # track name below (part_midi_meta), so `style` must always be bound.
    try:
        style = load_style(meta["style_id"])
    except (ValueError, KeyError):
        style = None
    part_cc = None
    if req.part != "drums":
        part_cc = _generate_part_cc(req.part, total_bars, channel, style=style)
        if req.part == "melody":
            part_cc = part_cc + _generate_melody_expression_cc(events, channel)
        # An edited stem keeps its pre-chorus sweeps/crescendo too
        for automation in (generate_build_sweeps(layout, [req.part]),
                           generate_section_crescendo(layout, [req.part])):
            part_cc = part_cc + automation.get(req.part, [])
    # A hand-drawn volume/pan curve (roadmap 9.3) overlays on top of all of the above —
    # including drums, which otherwise get no CC pass at all: every part now has its
    # own output insert (Slice 1), so drums can carry automation too even though they
    # skip the melodic pan/reverb/sweep treatment above. `[]` and `None` write
    # identically (write_midi's cc_events check is falsy either way), so this stays
    # byte-identical for drums when no automation is drawn.
    part_cc = _apply_automation_cc(part_cc or [], req.automation, channel)

    programs, track_names = part_midi_meta(style if style else {"id": meta.get("style_id", "")})
    write_midi(events, part_path, bpm=bpm, program=programs.get(req.part),
               cc_events=part_cc, tempo_events=tempo_map,
               track_name=track_names.get(req.part))

    rebuild_combined_from_parts(output_dir, bpm, combined_name="song.mid", meter=parse_meter(meta.get("time_signature", "4/4")), tempo_events=tempo_map,
                                markers=_section_markers(layout, meta.get("key", "C"), parse_meter(meta.get("time_signature", "4/4"))),
                                key_signature=mido_key_signature(meta.get("key", "C"), meta.get("scale", "minor")),
                                track_names=track_names)
    return FileInfo(part=req.part, filename=f"{req.part}.mid",
                    url=f"/exports/{req.generation_id}/{req.part}.mid")


def _song_response_from_dir(d) -> BuildSongResponse | None:
    """Rehydrate a BuildSongResponse from a song export folder, or None if the
    folder isn't a complete song (missing meta/structure/stems)."""
    meta_path = d / "song_meta.json"
    structure_path = d / "song_structure.json"
    if not (d.is_dir() and meta_path.exists() and structure_path.exists()):
        return None
    meta = _json_module.loads(meta_path.read_text())
    sections = _json_module.loads(structure_path.read_text())
    files = [FileInfo(part=f.stem, filename=f.name, url=f"/exports/{d.name}/{f.name}")
             for f in sorted(d.glob("*.mid"))]
    if not files:
        return None
    total_bars = sum(s.get("bars", 0) for s in sections)
    return BuildSongResponse(
        generation_id=d.name,
        style=meta.get("style_id", ""),
        files=files,
        seed=meta.get("base_seed", 0),
        template=meta.get("template", "verse_chorus"),
        total_bars=total_bars,
        sections=[SongSectionResult(**s) for s in sections],
        bpm=meta.get("bpm", 120),
        key=f"{meta.get('key', 'C')} {meta.get('scale', 'minor')}",
        progression=meta.get("song_progression"),
        mixer=meta.get("mixer") or {},
    )


@router.get("/songs", response_model=list[BuildSongResponse])
def list_songs(limit: int = 20):
    """Previously built songs, newest first, rehydrated from disk.

    Lets the UI survive a reload: song stems, structure, and regeneration
    context all live in the export folder, so the frontend can re-open any
    recent song exactly as it was (including its version history).
    """
    entries: list[tuple[float, BuildSongResponse]] = []
    if not EXPORTS_DIR.exists():
        return []
    for d in EXPORTS_DIR.iterdir():
        try:
            resp = _song_response_from_dir(d)
            if resp is None:
                continue
            entries.append(((d / "song_meta.json").stat().st_mtime, resp))
        except Exception:
            continue   # a half-written or legacy folder never breaks the list
    entries.sort(key=lambda e: e[0], reverse=True)
    return [r for _, r in entries[:limit]]


# ── Portable project files (.ggproj) ─────────────────────────────────────────
# A .ggproj is a plain zip capturing a whole song session — every part stem plus
# song_meta.json + song_structure.json (+ any section stems) — so a session can
# be archived or handed to another machine and re-opened faithfully. Version
# snapshots (versions/) are intentionally left out to keep the archive lean; an
# imported project starts a fresh undo history.
_MAX_PROJECT_BYTES = 200 * 1024 * 1024   # uncompressed cap (zip-bomb guard)
_MAX_PROJECT_ENTRIES = 2000


@router.get("/export-project/{generation_id}")
def export_project(generation_id: str):
    """Download a portable `.ggproj` (zip) for a whole song session."""
    import io
    import zipfile
    from fastapi.responses import StreamingResponse
    if not _SAFE_PATH.match(generation_id):
        raise HTTPException(status_code=400, detail="Invalid generation id")
    output_dir = EXPORTS_DIR / generation_id
    if _song_response_from_dir(output_dir) is None:
        raise HTTPException(status_code=404, detail="Song not found")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.json", _json_module.dumps({
            "format": "ggproj", "format_version": 1, "generation_id": generation_id,
        }))
        for name in ("song_meta.json", "song_structure.json"):
            f = output_dir / name
            if f.exists():
                zf.write(f, name)
        for f in sorted(output_dir.glob("*.mid")):
            zf.write(f, f.name)
        sec_dir = output_dir / "sections"
        if sec_dir.is_dir():
            for f in sorted(sec_dir.iterdir()):
                if f.is_file() and f.suffix in (".mid", ".json"):
                    zf.write(f, f"sections/{f.name}")
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="genregrid_{generation_id}.ggproj"'},
    )


def _is_safe_project_member(name: str) -> bool:
    """Accept only known, non-escaping members from an imported .ggproj."""
    if name.startswith("/") or "\\" in name or ".." in name.split("/"):
        return False   # absolute path, windows separator, or `..` traversal
    if name in ("song_meta.json", "song_structure.json", "project.json"):
        return True
    if name.endswith(".mid") and "/" not in name:
        return True
    if name.startswith("sections/") and name.count("/") == 1 and name.rsplit(".", 1)[-1] in ("mid", "json"):
        return True
    return False


@router.post("/import-project", response_model=BuildSongResponse)
async def import_project(file: UploadFile = FastAPIFile(...)):
    """Restore a `.ggproj` into a brand-new song folder (fresh generation id) and
    return it rehydrated, ready to open."""
    import io
    import zipfile
    data = await file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Not a valid .ggproj file")

    infos = [zi for zi in zf.infolist() if not zi.is_dir()]
    if len(infos) > _MAX_PROJECT_ENTRIES:
        raise HTTPException(status_code=400, detail="Project archive has too many files")
    if sum(zi.file_size for zi in infos) > _MAX_PROJECT_BYTES:
        raise HTTPException(status_code=400, detail="Project archive is too large")

    safe = {zi.filename: zi for zi in infos if _is_safe_project_member(zi.filename)}
    if "song_meta.json" not in safe or "song_structure.json" not in safe:
        raise HTTPException(status_code=400, detail="Project is missing song_meta.json or song_structure.json")
    if not any(n.endswith(".mid") and "/" not in n for n in safe):
        raise HTTPException(status_code=400, detail="Project has no part stems")

    gen_id = uuid.uuid4().hex
    output_dir = EXPORTS_DIR / gen_id
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        for name, zi in safe.items():
            if name == "project.json":
                continue   # manifest is metadata, not part of the restored session
            dest = output_dir / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(zi) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
        resp = _song_response_from_dir(output_dir)
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Project could not be restored")
    if resp is None:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Project could not be restored")
    return resp


_MAX_SONG_VERSIONS = 50   # deep, per-song undo within a session (was 5)
_VERSION_ID = re.compile(r"^\d{10,16}$")


def _snapshot_song(output_dir) -> None:
    """Snapshot every stem + metadata into versions/<ms> before a mutation.

    Keeps the last _MAX_SONG_VERSIONS so any re-roll / added part / restore can
    be stepped back from the History picker (deeper than the one-level .prev).
    """
    import time as _time
    versions_dir = output_dir / "versions"
    versions_dir.mkdir(exist_ok=True)
    snap = versions_dir / str(int(_time.time() * 1000))
    snap.mkdir(exist_ok=True)
    for f in output_dir.iterdir():
        if f.is_file() and (f.suffix == ".mid" or f.name in ("song_meta.json", "song_structure.json")):
            shutil.copy(f, snap / f.name)
    snaps = sorted((d for d in versions_dir.iterdir() if d.is_dir()), key=lambda d: d.name)
    for old_snap in snaps[:-_MAX_SONG_VERSIONS]:
        shutil.rmtree(old_snap, ignore_errors=True)


@router.get("/song-versions/{generation_id}")
def list_song_versions(generation_id: str):
    """Versions saved before each mutation, newest first."""
    from datetime import datetime
    if not _SAFE_PATH.match(generation_id):
        raise HTTPException(status_code=400, detail="Invalid generation id")
    versions_dir = EXPORTS_DIR / generation_id / "versions"
    if not versions_dir.exists():
        return []
    out = []
    for d in sorted((d for d in versions_dir.iterdir() if d.is_dir()),
                    key=lambda d: d.name, reverse=True):
        try:
            saved_at = datetime.fromtimestamp(int(d.name) / 1000).isoformat(timespec="seconds")
        except (ValueError, OSError):
            continue
        out.append({"id": d.name, "saved_at": saved_at})
    return out


@router.post("/restore-song-version", response_model=list[FileInfo])
def restore_song_version(req: RestoreSongVersionRequest):
    """Restore a snapshot. The current state is snapshotted first, so a restore
    is itself restorable."""
    if not _SAFE_PATH.match(req.generation_id) or not _VERSION_ID.match(req.version_id):
        raise HTTPException(status_code=400, detail="Invalid id")
    output_dir = EXPORTS_DIR / req.generation_id
    snap = output_dir / "versions" / req.version_id
    if not snap.exists():
        raise HTTPException(status_code=404, detail="Version not found")

    _snapshot_song(output_dir)
    snap_names = {f.name for f in snap.iterdir() if f.is_file()}
    for f in snap.iterdir():
        if f.is_file():
            shutil.copy(f, output_dir / f.name)
    # Stems created after this snapshot (e.g. a later-added part) must go too
    for f in output_dir.glob("*.mid"):
        if f.name not in snap_names:
            f.unlink()
    return [FileInfo(part=f.stem, filename=f.name,
                     url=f"/exports/{req.generation_id}/{f.name}")
            for f in sorted(output_dir.glob("*.mid"))]


@router.post("/undo-song-part", response_model=FileInfo)
def undo_song_part(req: RegenerateSongPartRequest):
    """Restore the previous version of a song stem (one level of undo)."""
    output_dir = EXPORTS_DIR / req.generation_id
    prev = output_dir / f"{req.part}.prev"
    if not prev.exists():
        raise HTTPException(status_code=404, detail="Nothing to undo for this part")
    meta_path = output_dir / "song_meta.json"
    meta = _json_module.loads(meta_path.read_text()) if meta_path.exists() else {}
    bpm = meta.get("bpm", 120)
    _layout = _template_section_results(meta.get("template", "verse_chorus"), meta.get("key", "C"),
                                        custom=meta.get("custom_template"))
    tempo_map = _song_tempo_map(_layout, bpm, ending_bars=1, meter=parse_meter(meta.get("time_signature", "4/4")), intensity=meta.get("tempo_automation", 0.5))

    shutil.copy(prev, output_dir / f"{req.part}.mid")
    prev.unlink()   # one level of undo only
    try:
        _, _track_names = part_midi_meta(load_style(meta.get("style_id", "")))
    except Exception:
        logger.warning("Could not load style %r for track names — using defaults",
                       meta.get("style_id", ""), exc_info=True)
        _track_names = {}
    rebuild_combined_from_parts(output_dir, bpm, combined_name="song.mid", meter=parse_meter(meta.get("time_signature", "4/4")), tempo_events=tempo_map,
                                markers=_section_markers(_layout, meta.get("key", "C"), parse_meter(meta.get("time_signature", "4/4"))),
                                key_signature=mido_key_signature(meta.get("key", "C"), meta.get("scale", "minor")),
                                track_names=_track_names)
    return FileInfo(part=req.part, filename=f"{req.part}.mid",
                    url=f"/exports/{req.generation_id}/{req.part}.mid")


@router.post("/regenerate-song-section", response_model=list[FileInfo])
def regenerate_song_section(req: RegenerateSongSectionRequest):
    """Re-roll one section of a built song, keeping every other section identical.

    Replaces the stored winning seed for that section and replays the song's
    section loop, so all parts of the target section get fresh music while the
    rest of the song reproduces byte-for-byte from the persisted seeds. Note the
    ripple rules: re-rolling the first occurrence of a section type also updates
    later sections of that type (they reuse its theme), and re-rolling a verse
    can reshape choruses (they develop the verse's motif) — musically intended.
    """
    output_dir = EXPORTS_DIR / req.generation_id
    meta_path = output_dir / "song_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Song not found or too old to regenerate")
    meta = _json_module.loads(meta_path.read_text())
    section_seeds = list(meta.get("section_seeds") or [])
    template = meta.get("custom_template") or _SONG_TEMPLATES.get(meta.get("template", ""), _SONG_TEMPLATES["verse_chorus"])
    if not section_seeds:
        raise HTTPException(status_code=400, detail="This song predates section re-roll — rebuild it once to enable")
    if not (0 <= req.section_index < len(template)):
        raise HTTPException(status_code=400, detail=f"section_index must be 0..{len(template) - 1}")

    try:
        style = load_style(meta["style_id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = max(bpm_min, min(bpm_max, meta["bpm"]))
    secondary_dominants = style.get("secondary_dominants", False)
    tritone_sub = style.get("tritone_substitution", False)
    groove_push = style.get("groove_push", 0.0)
    style = _blend_styles(style, meta.get("blend_style_id"), meta.get("blend_amount", 0.5))
    style = {**style, "_humanize_scale": meta["humanize"]}
    programs, track_names = part_midi_meta(style)

    _snapshot_song(output_dir)   # version history: state before this mutation

    section_seeds[req.section_index] = secrets.randbelow(2 ** 31)

    song_req = BuildSongRequest.model_construct(
        style_id=meta["style_id"], key=meta["key"], scale=meta["scale"], bpm=meta["bpm"],
        time_signature=meta.get("time_signature", "4/4"),
        complexity=meta["complexity"], variation=meta["variation"], humanize=meta["humanize"],
        dynamics=meta.get("dynamics", 0.5),
        parts=meta["parts"], template=meta["template"], use_priors=meta["use_priors"],
        seed=meta["base_seed"], chorus_key_shift=meta["chorus_key_shift"],
    )
    song_events, section_results, total_bars, _seeds, _prog = _generate_song_sections(
        song_req, style, bpm, meta["base_seed"], meta["chorus_key_shift"],
        secondary_dominants, tritone_sub, groove_push,
        bridge_key_shift=meta.get("bridge_key_shift", 0),
        fixed_section_seeds=section_seeds,
        final_chorus_lift=meta.get("final_chorus_lift", 0),
        custom_template=meta.get("custom_template"),
        # Pin the persisted progression so re-rolling a section keeps the song's harmony.
        user_progression=meta.get("song_progression") or meta.get("user_progression"),
        hook_melody=_hook_from_meta(meta),
    )

    # Back up all stems (one level of undo per part via /undo-song-part)
    for part in meta["parts"]:
        p = output_dir / f"{part}.mid"
        if p.exists():
            shutil.copy(p, output_dir / f"{part}.prev")

    files = _write_song_output(song_events, output_dir, req.generation_id, bpm, style,
                               programs, list(meta["parts"]), total_bars, section_results,
                               key=meta.get("key", "C"), scale=meta.get("scale", "minor"),
                               meter=parse_meter(meta.get("time_signature", "4/4")),
                               tempo_automation=meta.get("tempo_automation", 0.5))

    # Part locking: any locked stem is restored to its pre-reroll state (the .prev
    # backup taken above) so it stays byte-identical — the section re-roll only
    # rewrites the unlocked parts. song.mid is then rebuilt from the on-disk stems
    # (locked = old, unlocked = fresh) so playback matches.
    locked = [p for p in (req.locked_parts or []) if p in meta["parts"]]
    if locked:
        for part in locked:
            prev = output_dir / f"{part}.prev"
            if prev.exists():
                shutil.copy(prev, output_dir / f"{part}.mid")
        rebuild_combined_from_parts(
            output_dir, bpm, combined_name="song.mid", meter=parse_meter(meta.get("time_signature", "4/4")),
            tempo_events=_song_tempo_map(section_results, bpm, ending_bars=1, meter=parse_meter(meta.get("time_signature", "4/4")), intensity=meta.get("tempo_automation", 0.5)),
            markers=_section_markers(section_results, meta.get("key", "C"), parse_meter(meta.get("time_signature", "4/4"))),
            key_signature=mido_key_signature(meta.get("key", "C"), meta.get("scale", "minor")),
            track_names=track_names)
        # Don't ask the client to reload a locked stem that didn't change.
        files = [f for f in files if f.part not in locked]

    meta["section_seeds"] = section_seeds
    meta_path.write_text(_json_module.dumps(meta))
    (output_dir / "song_structure.json").write_text(_json_module.dumps(section_results, indent=2))
    return files


@router.post("/rearrange-song-sections", response_model=BuildSongResponse)
def rearrange_song_sections(req: RearrangeSongSectionsRequest):
    """Reorder / insert / delete / duplicate / resize a song's section timeline
    (roadmap item 9.2, first slice).

    Builds a new section template from `req.sections` and does a full in-place
    regeneration of the song from it (same approach as /regenerate-song-section),
    reusing each surviving section's ORIGINAL seed (via `source_index`) for
    content stability — the same section content just plays in its new position/
    length — while brand-new sections (no `source_index`) get a fresh quality-
    searched seed. Ripple rules still apply naturally (a moved verse can still
    reshape a later chorus that develops its motif, a section moved to be the
    first-of-its-type now sets the theme for later repeats) because the whole
    song replays in the new template order, same as a section re-roll.

    Blocked (400) if any part is locked — a structural edit invalidates content
    at fixed bar positions, so there's nothing sensible to preserve; unlock
    first.
    """
    output_dir = EXPORTS_DIR / req.generation_id
    meta_path = output_dir / "song_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Song not found or too old to rearrange")
    meta = _json_module.loads(meta_path.read_text())

    old_section_seeds = list(meta.get("section_seeds") or [])
    old_template = meta.get("custom_template") or _SONG_TEMPLATES.get(
        meta.get("template", ""), _SONG_TEMPLATES["verse_chorus"])
    if not old_section_seeds:
        raise HTTPException(status_code=400,
                            detail="This song predates section editing — rebuild it once to enable")

    locked = [p for p in (req.locked_parts or []) if p in meta.get("parts", [])]
    if locked:
        raise HTTPException(status_code=400,
                            detail=f"Unlock {', '.join(locked)} before rearranging — a structural "
                                   f"edit invalidates locked bar positions")

    for sd in req.sections:
        if sd.source_index is not None and not (0 <= sd.source_index < len(old_template)):
            raise HTTPException(status_code=400, detail=f"source_index out of range: {sd.source_index}")

    try:
        style = load_style(meta["style_id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = max(bpm_min, min(bpm_max, meta["bpm"]))
    secondary_dominants = style.get("secondary_dominants", False)
    tritone_sub = style.get("tritone_substitution", False)
    groove_push = style.get("groove_push", 0.0)
    style = _blend_styles(style, meta.get("blend_style_id"), meta.get("blend_amount", 0.5))
    style = {**style, "_humanize_scale": meta["humanize"]}
    programs, track_names = part_midi_meta(style)

    _snapshot_song(output_dir)   # version history: state before this mutation — makes this undoable

    new_template, fixed_seeds = [], []
    for sd in req.sections:
        new_template.append(sd.model_dump(exclude={"source_index"}))
        if sd.source_index is not None and sd.source_index < len(old_section_seeds):
            fixed_seeds.append(old_section_seeds[sd.source_index])
        else:
            fixed_seeds.append(None)   # brand-new content: fresh quality-searched seed

    song_req = BuildSongRequest.model_construct(
        style_id=meta["style_id"], key=meta["key"], scale=meta["scale"], bpm=meta["bpm"],
        time_signature=meta.get("time_signature", "4/4"),
        complexity=meta["complexity"], variation=meta["variation"], humanize=meta["humanize"],
        dynamics=meta.get("dynamics", 0.5),
        parts=meta["parts"], template=meta["template"], use_priors=meta["use_priors"],
        seed=meta["base_seed"], chorus_key_shift=meta["chorus_key_shift"],
        dj_edit=meta.get("dj_edit", False),
    )
    song_events, section_results, total_bars, section_seeds, _prog = _generate_song_sections(
        song_req, style, bpm, meta["base_seed"], meta["chorus_key_shift"],
        secondary_dominants, tritone_sub, groove_push,
        bridge_key_shift=meta.get("bridge_key_shift", 0),
        fixed_section_seeds=fixed_seeds,
        final_chorus_lift=meta.get("final_chorus_lift", 0),
        custom_template=new_template,
        # Pin the persisted progression so rearranging keeps the song's harmony.
        user_progression=meta.get("song_progression") or meta.get("user_progression"),
        hook_melody=_hook_from_meta(meta),
    )

    files = _write_song_output(song_events, output_dir, req.generation_id, bpm, style,
                               programs, list(meta["parts"]), total_bars, section_results,
                               key=meta.get("key", "C"), scale=meta.get("scale", "minor"),
                               meter=parse_meter(meta.get("time_signature", "4/4")),
                               tempo_automation=meta.get("tempo_automation", 0.5))

    meta["custom_template"] = new_template
    meta["template"] = "custom"   # the named template no longer describes this layout
    meta["section_seeds"] = section_seeds
    meta_path.write_text(_json_module.dumps(meta))
    (output_dir / "song_structure.json").write_text(_json_module.dumps(section_results, indent=2))

    return BuildSongResponse(
        generation_id=req.generation_id, style=meta["style_id"], files=files,
        seed=meta["base_seed"], template="custom", total_bars=total_bars,
        sections=[SongSectionResult(**s) for s in section_results],
        bpm=bpm, key=f"{meta.get('key', 'C')} {meta.get('scale', 'minor')}",
        progression=meta.get("song_progression") or meta.get("user_progression"),
    )
