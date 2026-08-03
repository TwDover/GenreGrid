# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
import concurrent.futures
import io
import logging
import random
import re
import secrets
import uuid
import json as _json_module
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from app.models.schemas import GenerateRequest, RegeneratePartRequest, GenerateResponse, FileInfo, GenerateSummary, QualityScore, BatchGenerateRequest
from app.services.style_loader import load_style
from app.services.midi_writer import NoteEvent, write_midi, write_combined_midi, rebuild_combined_from_parts, concatenate_midi_files, read_note_starts, mido_key_signature
from app.core.meter import parse_meter
from app.generators.chords import generate_chords, resolve_progression
from app.generators.bass import generate_bass
from app.generators.melody import generate_melody
from app.generators.drums import generate_drums
from app.generators.arpeggio import generate_arpeggio
from app.generators.pads import generate_pads
from app.generators.counter_melody import generate_counter_melody
from app.core.config import EXPORTS_DIR
from app.core.constants import DRUM_MAP
from app.services.priors import melody_prior_for
from app.services.library import save_generation as lib_save, build_scoring_style
from app.core.arrangement import (
    _part_seed, _plan_sections, _section_end_bars,
)
from app.services.mixdown import (
    _PART_CHANNELS, part_midi_meta,
    _generate_part_cc, _generate_melody_expression_cc, _generate_bass_expression_cc,
    _generate_808_pitch_bends, _drop_quiet, _scale_velocity, _shift,
    _apply_groove_push, _apply_dynamic,
)

from app.services.generation import (
    _chord_tones_by_bar, _MAX_QUALITY_ATTEMPTS, _GENERATION_TIMEOUT_S, _all_green,
    _blend_styles, _prior_name, _overlay_groove,
    _choose_progression, _run_attempt,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
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
    is_loop = (req.mode == "loop")
    groove_push = style.get("groove_push", 0.0)
    # The generators already place events in this meter (see services.generation);
    # thread it to the writer too so the .mid's time_signature meta matches instead
    # of always claiming 4/4. 4/4 → DEFAULT_METER, byte-identical.
    meter = parse_meter(getattr(req, "time_signature", None))

    style = _blend_styles(style, req.blend_style_id, req.blend_amount)

    # Inject humanize scale so generators can read it without API changes
    style = {**style, "_humanize_scale": req.humanize}

    # Use custom progression if provided (validate roman numerals loosely)
    if req.custom_progression:
        style = {**style, "progression_templates": [req.custom_progression]}

    # Use library-learned patterns to sharpen the scorer's rhythm references
    scoring_style = build_scoring_style(style, req.style_id)

    # Start with the requested seed (or a fresh random one)
    base_seed = req.seed if req.seed is not None else random.randint(0, 2**31 - 1)

    def _run_best_attempt():
        _best_events = _best_cc = _best_pb = _best_progression = _best_quality_raw = _best_patterns = None
        _best_seed = base_seed
        for attempt in range(_MAX_QUALITY_ATTEMPTS):
            # Deterministic retry seeds: a given base seed always reproduces the
            # same attempt sequence (global-RNG retries made seeded generations
            # unreproducible whenever the quality gate triggered a retry).
            attempt_seed = base_seed if attempt == 0 else _part_seed(base_seed, attempt, "retry")
            _evts, _cc, _pb, _prog, _qraw, _pats, _secs = _run_attempt(
                req, style, attempt_seed, is_loop, groove_push, secondary_dominants, tritone_sub,
                scoring_style=scoring_style,
            )
            if _best_quality_raw is None or (
                _qraw is not None and _qraw.get("total", 0) > _best_quality_raw.get("total", 0)
            ):
                _best_events, _best_cc, _best_pb = _evts, _cc, _pb
                _best_progression, _best_quality_raw = _prog, _qraw
                _best_patterns, _best_sections = _pats, _secs
                _best_seed = attempt_seed
            if _qraw is not None and _all_green(_qraw):
                _best_seed = attempt_seed
                break
        return _best_events, _best_cc, _best_pb, _best_progression, _best_quality_raw, _best_patterns, _best_sections, _best_seed

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
            _fut = _pool.submit(_run_best_attempt)
            (best_events, best_cc, best_pb, best_progression,
             best_quality_raw, best_patterns, best_sections, best_seed) = _fut.result(timeout=_GENERATION_TIMEOUT_S)
    except concurrent.futures.TimeoutError:
        raise HTTPException(status_code=504, detail=f"Generation timed out after {_GENERATION_TIMEOUT_S}s")

    all_events  = best_events
    cc_parts    = best_cc
    pb_parts    = best_pb
    progression = best_progression
    quality_raw = best_quality_raw
    patterns    = best_patterns
    seed        = best_seed

    quality = QualityScore(**quality_raw) if quality_raw else None

    import json as _json

    # Write patterns.json so the frontend's manual-save can retrieve them later
    (output_dir / "patterns.json").write_text(_json.dumps(patterns or {}))
    # meta.json lets a later download/thumbs-up record a library keep without the
    # frontend re-sending the generation parameters (roadmap-2 item 9).
    (output_dir / "meta.json").write_text(_json.dumps({
        "style_id": req.style_id, "key": req.key, "scale": req.scale,
        "bpm": bpm, "bars": req.bars, "seed": seed,
        "quality": quality_raw or {},
    }))

    # Auto-save to library when all dimensions are green
    if quality_raw and _all_green(quality_raw):
        try:
            lib_save(
                gen_id=gen_id,
                style_id=req.style_id,
                key=req.key,
                scale=req.scale,
                bpm=bpm,
                bars=req.bars,
                seed=seed,
                quality_raw=quality_raw,
                patterns=patterns or {},
            )
        except Exception as exc:
            logger.warning("Library auto-save failed for gen_id=%s: %s", gen_id, exc)

    _sid = style.get("id", "")
    files = []
    for part, events in all_events.items():
        if not events:
            continue
        events = _scale_velocity(events, part, _sid)
        events = _drop_quiet(events)
        filename = f"{part}.mid"
        out_path = output_dir / filename
        write_midi(events, out_path, bpm=bpm, program=programs.get(part),
                   cc_events=cc_parts.get(part), pb_events=pb_parts.get(part),
                   track_name=track_names.get(part), meter=meter)
        files.append(FileInfo(part=part, filename=filename, url=f"/exports/{gen_id}/{filename}"))

    if len(all_events) > 1:
        combined_path = output_dir / "combined.mid"
        clean_events = {p: _drop_quiet(_scale_velocity(e, p, _sid)) for p, e in all_events.items()}
        write_combined_midi(clean_events, combined_path, bpm=bpm, programs=programs,
                           cc_parts=cc_parts, pb_parts=pb_parts, track_names=track_names, meter=meter,
                           key_signature=mido_key_signature(req.key, req.scale))
        files.append(FileInfo(part="combined", filename="combined.mid", url=f"/exports/{gen_id}/combined.mid"))

    # In arrangement mode, also write per-section MIDI files
    if not is_loop and best_sections:
        sec_dir = output_dir / "sections"
        sec_dir.mkdir(exist_ok=True)
        import json as _js
        section_meta = []
        for sec_i, sec in enumerate(best_sections):
            sec_start = float(sec["offset"])
            sec_end = sec_start + sec["bars"] * 4.0
            sec_name = sec.get("section_type", f"section_{sec_i + 1}")
            sec_evts: dict[str, list] = {}
            for part, evts in all_events.items():
                clipped = [
                    NoteEvent(e.pitch, e.start - sec_start, e.duration, e.velocity, e.channel)
                    for e in evts
                    if sec_start <= e.start < sec_end
                ]
                if clipped:
                    sec_evts[part] = _drop_quiet(_scale_velocity(clipped, part, _sid))
            if sec_evts:
                sec_combined = sec_dir / f"{sec_i + 1:02d}_{sec_name}_combined.mid"
                write_combined_midi(sec_evts, sec_combined, bpm=bpm, programs=programs, track_names=track_names)
                section_meta.append({
                    "index": sec_i + 1, "name": sec_name,
                    "bars": sec["bars"], "bpm": bpm,
                    "file": sec_combined.name,
                })
        (sec_dir / "sections.json").write_text(_js.dumps(section_meta, indent=2))

    return GenerateResponse(
        generation_id=gen_id,
        style=req.style_id,
        files=files,
        summary=GenerateSummary(
            key=f"{req.key} {req.scale}",
            key_root=req.key,
            scale=req.scale,
            bpm=bpm,
            bars=req.bars,
            complexity=req.complexity,
            variation=req.variation,
            mode=req.mode,
            section_type=req.section_type,
        ),
        seed=seed,
        quality=quality,
        auto_saved=bool(quality_raw and _all_green(quality_raw)),
        progression=progression,
    )


@router.post("/generate-stream")
def generate_stream(req: GenerateRequest):
    """SSE endpoint: streams attempt progress then the final GenerateResponse."""
    def event_stream():
        try:
            style = load_style(req.style_id)
        except ValueError as e:
            yield f"data: {_json_module.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        bpm_min, bpm_max = style.get("bpm_range", [40, 240])
        bpm = max(bpm_min, min(bpm_max, req.bpm))
        gen_id = str(uuid.uuid4())[:8]
        output_dir = EXPORTS_DIR / gen_id
        output_dir.mkdir(parents=True, exist_ok=True)

        programs, track_names = part_midi_meta(style)
        secondary_dominants = style.get("secondary_dominants", False)
        tritone_sub = style.get("tritone_substitution", False)
        is_loop = (req.mode == "loop")
        groove_push = style.get("groove_push", 0.0)
        meter = parse_meter(getattr(req, "time_signature", None))
        style = {**style, "_humanize_scale": req.humanize}
        if req.custom_progression:
            style = {**style, "progression_templates": [req.custom_progression]}
        scoring_style = build_scoring_style(style, req.style_id)
        base_seed = req.seed if req.seed is not None else random.randint(0, 2**31 - 1)

        best_events = best_cc = best_pb = best_progression = best_quality_raw = best_patterns = None
        best_seed = base_seed

        for attempt in range(_MAX_QUALITY_ATTEMPTS):
            # Deterministic retry seeds: a given base seed always reproduces the
            # same attempt sequence (global-RNG retries made seeded generations
            # unreproducible whenever the quality gate triggered a retry).
            attempt_seed = base_seed if attempt == 0 else _part_seed(base_seed, attempt, "retry")
            yield f"data: {_json_module.dumps({'type': 'progress', 'attempt': attempt + 1, 'total': _MAX_QUALITY_ATTEMPTS})}\n\n"
            try:
                evts, cc, pb, prog, qraw, pats, secs = _run_attempt(
                    req, style, attempt_seed, is_loop, groove_push,
                    secondary_dominants, tritone_sub, scoring_style=scoring_style,
                )
            except Exception as exc:
                logger.error("Attempt %d failed: %s", attempt + 1, exc, exc_info=True)
                continue
            if best_quality_raw is None or (qraw and qraw.get("total", 0) > best_quality_raw.get("total", 0)):
                best_events, best_cc, best_pb = evts, cc, pb
                best_progression, best_quality_raw, best_patterns = prog, qraw, pats
                best_seed = attempt_seed
            if qraw and _all_green(qraw):
                best_seed = attempt_seed
                break

        quality = QualityScore(**best_quality_raw) if best_quality_raw else None
        if best_quality_raw and _all_green(best_quality_raw):
            try:
                lib_save(gen_id=gen_id, style_id=req.style_id, key=req.key, scale=req.scale,
                         bpm=bpm, bars=req.bars, seed=best_seed,
                         quality_raw=best_quality_raw, patterns=best_patterns or {})
            except Exception as exc:
                logger.warning("Library auto-save failed: %s", exc)
        (output_dir / "patterns.json").write_text(_json_module.dumps(best_patterns or {}))

        _sid = style.get("id", "")
        files = []
        for part, events in (best_events or {}).items():
            if not events:
                continue
            events = _scale_velocity(events, part, _sid)
            events = _drop_quiet(events)
            filename = f"{part}.mid"
            write_midi(events, output_dir / filename, bpm=bpm,
                       program=programs.get(part),
                       cc_events=(best_cc or {}).get(part),
                       pb_events=(best_pb or {}).get(part),
                       track_name=track_names.get(part), meter=meter)
            files.append(FileInfo(part=part, filename=filename, url=f"/exports/{gen_id}/{filename}"))

        if best_events and len(best_events) > 1:
            combined_path = output_dir / "combined.mid"
            clean = {p: _drop_quiet(_scale_velocity(e, p, _sid)) for p, e in best_events.items()}
            write_combined_midi(clean, combined_path, bpm=bpm, programs=programs,
                               cc_parts=best_cc or {}, pb_parts=best_pb or {},
                               track_names=track_names, meter=meter,
                               key_signature=mido_key_signature(req.key, req.scale))
            files.append(FileInfo(part="combined", filename="combined.mid",
                                  url=f"/exports/{gen_id}/combined.mid"))

        response = GenerateResponse(
            generation_id=gen_id, style=req.style_id, files=files,
            summary=GenerateSummary(key=f"{req.key} {req.scale}", key_root=req.key,
                                    scale=req.scale, time_signature=getattr(req, "time_signature", "4/4"),
                                    bpm=bpm, bars=req.bars,
                                    complexity=req.complexity, variation=req.variation,
                                    mode=req.mode, section_type=req.section_type),
            seed=best_seed, quality=quality,
            auto_saved=bool(best_quality_raw and _all_green(best_quality_raw)),
            progression=best_progression or [],
        )
        yield f"data: {_json_module.dumps({'type': 'done', 'result': response.model_dump()})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/batch-generate", response_model=list[GenerateResponse])
def batch_generate(req: BatchGenerateRequest):
    """Run `count` independent generations and return all results sorted best-first."""
    results = []
    for _ in range(req.count):
        seed_req = GenerateRequest(**{**req.base.model_dump(), "seed": None})
        results.append(generate(seed_req))
    results.sort(key=lambda r: r.quality.total if r.quality else 0.0, reverse=True)
    return results


@router.post("/regenerate-part", response_model=FileInfo)
def regenerate_part(req: RegeneratePartRequest):
    output_dir = EXPORTS_DIR / req.generation_id
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail="Generation not found")

    try:
        style = load_style(req.style_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    style = _overlay_groove(style, getattr(req, "use_priors", True))
    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = max(bpm_min, min(bpm_max, req.bpm))

    # Replay the original seed so we pick the same progression and substitutions —
    # keeps harmony consistent with the other parts generated from that seed.
    progression = _choose_progression(style, getattr(req, "use_priors", True), req.seed, req.scale)

    secondary_dominants = style.get("secondary_dominants", False)
    tritone_sub = style.get("tritone_substitution", False)

    # New independent seed for just this part — use OS entropy so it's different
    # every call regardless of what req.seed was.
    new_seed = secrets.randbelow(2**31)
    random.seed(new_seed)

    programs, track_names = part_midi_meta(style)
    if req.mode == "loop":
        sections = [{"bars": req.bars, "complexity": req.complexity, "parts": [req.part], "offset": 0, "key": req.key}]
    else:
        key_shift = style.get("chorus_key_shift", 0)
        sections = _plan_sections(req.bars, req.complexity, [req.part], req.key, key_shift)
    events: list[NoteEvent] = []

    # Detect if melody.mid already exists alongside the regenerated part so
    # arpeggio can be pushed to a higher octave to avoid register conflict.
    melody_exists = (output_dir / "melody.mid").exists()

    # When regenerating the arpeggio, read the already-saved chords so the new arp
    # arpeggiates the real voiced harmony (matching extensions) rather than a plain
    # triad. Built once as an absolute per-bar map, sliced per section below.
    global_chord_tones: list | None = None
    if req.part == "arpeggio":
        chords_path = output_dir / "chords.mid"
        if chords_path.exists():
            try:
                global_chord_tones = _chord_tones_by_bar(read_note_starts(chords_path), req.bars)
            except Exception:
                logger.debug("Could not derive chord tones for arpeggio from %s", chords_path, exc_info=True)
                global_chord_tones = None

    for section_i, section in enumerate(sections):
        s_bars  = section["bars"]
        s_cplx  = section["complexity"]
        s_parts = set(section["parts"])
        s_off   = section["offset"]
        s_key   = section.get("key", req.key)
        if req.part not in s_parts:
            continue

        # Re-resolve substitutions with this section's complexity so the
        # regenerated part stays harmonically aligned with the original session.
        # Resolved on the same deterministic "harmony" seed _run_attempt used when the
        # sibling parts were first generated (isolated via save/restore so it doesn't
        # perturb the independent content randomness this regenerated part should get).
        saved_content_state = random.getstate()
        random.seed(_part_seed(req.seed, section_i, "harmony"))
        s_resolved = resolve_progression(progression, req.scale, s_cplx, secondary_dominants, tritone_sub)
        random.setstate(saved_content_state)

        kick_times: list[float] = []
        if req.part in ("bass", "chords"):
            saved_state = random.getstate()
            random.seed(_part_seed(req.seed, section_i, "drums"))
            drum_evts_tmp = generate_drums(style, s_bars, s_cplx, req.variation,
                                           section_end_bars=_section_end_bars(sections, s_off),
                                           dynamics=getattr(req, "dynamics", 0.5))
            kick_times = [e.start for e in drum_evts_tmp if e.pitch == DRUM_MAP["kick"]]
            random.setstate(saved_state)

        s_dyn = section.get("dynamic", 1.0)

        if req.part == "chords":
            evts = generate_chords(style, s_key, req.scale, s_bars, s_cplx,
                                   req.variation, progression, s_resolved,
                                   kick_times=kick_times)
        elif req.part == "bass":
            evts = generate_bass(style, s_key, req.scale, s_bars, s_cplx,
                                 req.variation, progression, kick_times)
        elif req.part == "melody":
            evts = generate_melody(style, s_key, req.scale, s_bars, s_cplx,
                                   req.variation, s_resolved,
                                   melody_model=melody_prior_for(_prior_name(style),
                                                                 getattr(req, "use_priors", True)))
        elif req.part == "pads":
            evts = generate_pads(style, s_key, req.scale, s_bars, s_cplx,
                                 req.variation, s_resolved)
        elif req.part == "counter_melody":
            # Rebuild the sibling melody deterministically (same part-seed the
            # original generation used) so the re-rolled harmony line tracks the
            # melody that's actually on disk.
            saved_cm_state = random.getstate()
            random.seed(_part_seed(req.seed, section_i, "melody"))
            sib_mel = generate_melody(style, s_key, req.scale, s_bars, s_cplx,
                                      req.variation, s_resolved,
                                      melody_model=melody_prior_for(_prior_name(style),
                                                                    getattr(req, "use_priors", True)))
            random.setstate(saved_cm_state)
            evts = generate_counter_melody(sib_mel, s_key, req.scale, s_bars,
                                           s_resolved, style)
        elif req.part == "drums":
            evts = generate_drums(style, s_bars, s_cplx, req.variation,
                                  section_end_bars=_section_end_bars(sections, s_off),
                                  dynamics=getattr(req, "dynamics", 0.5))
        elif req.part == "arpeggio":
            arp_octave = 6 if melody_exists else 5
            sec_tones = None
            if global_chord_tones:
                start_bar = int(s_off // 4)
                sec_tones = global_chord_tones[start_bar:start_bar + s_bars] or None
            evts = generate_arpeggio(style, s_key, req.scale, s_bars, s_cplx,
                                     req.variation, s_resolved, arp_octave,
                                     chord_tones=sec_tones)
        else:
            continue
        evts = _apply_dynamic(evts, s_dyn)
        events.extend(_shift(evts, s_off))

    groove_push = style.get("groove_push", 0.0)
    if groove_push and req.part in ("melody", "chords", "arpeggio", "bass"):
        events = _apply_groove_push(events, groove_push)

    events = _scale_velocity(events, req.part, style.get("id", ""))
    events = _drop_quiet(events)

    channel = _PART_CHANNELS.get(req.part, 0)
    part_cc = _generate_part_cc(req.part, req.bars, channel, style=style) if req.part != "drums" else None

    if req.part == "melody" and events:
        cc11 = _generate_melody_expression_cc(events, channel)
        part_cc = (part_cc or []) + cc11

    pb_events = None
    if req.part == "bass":
        bass_cfg = style.get("bass", {})
        if bass_cfg.get("bass_style") == "808":
            pb_events = _generate_808_pitch_bends(events, channel)
        elif events:
            bass_cc11 = _generate_bass_expression_cc(events, channel)
            part_cc = (part_cc or []) + bass_cc11

    filename = f"{req.part}.mid"
    out_path = output_dir / filename
    write_midi(events, out_path, bpm=bpm, program=programs.get(req.part),
               cc_events=part_cc, pb_events=pb_events,
               track_name=track_names.get(req.part))

    # Rebuild combined.mid so it reflects the newly regenerated part
    rebuild_combined_from_parts(output_dir, bpm, track_names=track_names)

    return FileInfo(part=req.part, filename=filename, url=f"/exports/{req.generation_id}/{filename}")


# Generation ids are short uuid4 hex slices (see /generate); keep the check strict
# but tolerant of any hex/underscore/hyphen id we've ever minted.
_VALID_GEN_ID = re.compile(r'^[A-Za-z0-9_\-]{1,64}$')


def _safe_export_dir(gen_id: str) -> Path:
    """Resolve EXPORTS_DIR/<gen_id> and guarantee it stays inside EXPORTS_DIR.

    Blocks path traversal via `..`/encoded separators in the id before any
    filesystem access. Raises 422 for a malformed id, 404 if the dir is missing.
    """
    if not _VALID_GEN_ID.match(gen_id):
        raise HTTPException(status_code=422, detail="Invalid generation id")
    root = EXPORTS_DIR.resolve()
    target = (root / gen_id).resolve()
    if not target.is_relative_to(root):
        raise HTTPException(status_code=404, detail="Generation not found")
    return target


@router.get("/exports/{gen_id}/bundle.zip")
def download_bundle(gen_id: str):
    import zipfile
    import io
    output_dir = _safe_export_dir(gen_id)
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail="Generation not found")
    mid_files = list(output_dir.glob("*.mid"))
    if not mid_files:
        raise HTTPException(status_code=404, detail="No MIDI files found")
    # Downloading the bundle is a deliberate keep — feed it to the library.
    from app.api.routes_library import record_export_keep
    record_export_keep(gen_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(mid_files):
            zf.write(f, f.name)
    buf.seek(0)
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=genregrid_{gen_id}.zip"},
    )


@router.get("/exports/{gen_id}/sections.zip")
def download_sections(gen_id: str):
    import zipfile
    import io
    sec_dir = _safe_export_dir(gen_id) / "sections"
    if not sec_dir.exists():
        raise HTTPException(status_code=404, detail="No section stems found — generate in Arrangement mode first")
    mid_files = list(sec_dir.glob("*.mid"))
    if not mid_files:
        raise HTTPException(status_code=404, detail="No section MIDI files found")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(mid_files):
            zf.write(f, f"sections/{f.name}")
        meta = sec_dir / "sections.json"
        if meta.exists():
            zf.write(meta, "sections/sections.json")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=genregrid_{gen_id}_sections.zip"},
    )


@router.get("/exports/{gen_id}/{filename}")
def download_export(gen_id: str, filename: str):
    base = _safe_export_dir(gen_id).resolve()
    file_path = (base / filename).resolve()
    # Reject any filename that escapes the generation dir (e.g. `..%2f..%2fsecret`).
    if not file_path.is_relative_to(base):
        raise HTTPException(status_code=404, detail="File not found")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = "audio/wav" if file_path.suffix == ".wav" else "audio/midi"
    return FileResponse(str(file_path), media_type=media_type, filename=file_path.name)


_SAFE_PATH = re.compile(r'^[a-zA-Z0-9_\-]{1,80}$')


class ArrangeEntry(BaseModel):
    generation_id: str
    filename: str


class ArrangeRequest(BaseModel):
    entries: list[ArrangeEntry]


@router.post("/arrange")
def arrange(req: ArrangeRequest):
    """Concatenate multiple MIDI files sequentially into an arrangement."""
    if not req.entries:
        raise HTTPException(400, "No entries provided")

    paths = []
    for entry in req.entries:
        if not _SAFE_PATH.match(entry.generation_id):
            raise HTTPException(400, f"Invalid generation_id: {entry.generation_id!r}")
        safe_name = entry.filename.replace("/", "").replace("\\", "")
        path = EXPORTS_DIR / entry.generation_id / safe_name
        if not path.exists():
            raise HTTPException(404, f"File not found: {entry.generation_id}/{safe_name}")
        paths.append(path)

    try:
        out_mid = concatenate_midi_files(paths)
    except Exception as exc:
        logger.error("arrange failed: %s", exc)
        raise HTTPException(500, "Failed to build arrangement") from exc

    buf = io.BytesIO()
    out_mid.save(file=buf)
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="audio/midi",
        headers={"Content-Disposition": "attachment; filename=arrangement.mid"},
    )
