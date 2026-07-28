#!/usr/bin/env python3
# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Build velocity-layered sample sets for GenreGrid's sampled instruments.

Tone.Sampler only scales one sample's gain by velocity, so a soft and a hard note
sound identical but louder. GenreGrid's LayeredSampler (frontend/src/soundfonts/
layeredSampler.ts) instead plays a different sample per velocity range — real
dynamics — driven by a `velocity.json` manifest next to the samples. This script
produces those layered sets: it downloads a source library's multi-dynamic WAVs,
converts each to a trimmed, peak-normalised mono MP3 (matching the existing sample
format), lays them out under frontend/public/samples/.../<layer>/, and writes the
manifest.

Instruments whose set has NO velocity.json keep playing as a single legacy layer,
so this only needs to run for instruments you're upgrading.

Requirements (dev-only; not part of the app):
    pip install numpy soundfile lameenc

Usage (from repo root):
    python scripts/build_velocity_samples.py                 # all specs below
    python scripts/build_velocity_samples.py vibraphone      # one instrument
    python scripts/build_velocity_samples.py --list

SOURCES & LICENSING. Each spec names its source and license. Only CC0 / CC-BY
sources are wired in here so the produced MP3s can ship alongside the GPL code
(samples are data, licensed separately — see DATA_LICENSES.md). Do not add a
source here without confirming its license permits redistribution; in particular
NonCommercial (CC BY-NC-*) sets are NOT acceptable, however good they sound.

NOTE NAMES. Several of these libraries name their files an octave away from the
pitch they actually sound (bass parts notated 8va; Versilian's C3-is-middle-C
convention). Every spec therefore carries an explicit `shift`, verified by
measuring each source's fundamental — never trust the filename. `shift` is the
semitone offset from the SOURCE spelling to real (scientific) pitch, which is
what Tone.Sampler needs to map a zone correctly.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf
import lameenc

REPO = Path(__file__).parent.parent
SAMPLES_DIR = REPO / "frontend" / "public" / "samples"
CACHE = REPO / ".sample-cache"          # downloaded source audio (git-ignored)

# ── Conversion settings ──────────────────────────────────────────────────────
TRIM_THRESHOLD_DB = -45.0   # trim leading/trailing audio quieter than this
TAIL_PAD_S = 0.15           # keep this much tail after the last loud sample
PEAK_DB = -1.0              # normalise each NOTE (across its layers) to this peak
MAX_TAIL_S = 6.0            # cap very long rings so files stay small
MP3_BITRATE = 128

# ── Note names ───────────────────────────────────────────────────────────────
# Output spelling is flats-only: '#' is awkward in a URL and Tone parses either.
_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
_PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def to_midi(name: str) -> int:
    m = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d+)", name)
    if not m:
        raise ValueError(f"unparseable note name: {name!r}")
    letter, accidental, octave = m.group(1).upper(), m.group(2), int(m.group(3))
    return _PITCH_CLASS[letter] + {"#": 1, "b": -1, "": 0}[accidental] + (octave + 1) * 12


def to_name(midi: int) -> str:
    return f"{_NAMES[midi % 12]}{midi // 12 - 1}"


@dataclass
class Layer:
    """One velocity layer: an inclusive upper velocity bound (0..1) and the source
    file (relative to the spec's base URL) for each note, keyed by the note name
    the OUTPUT uses. A list value gives that note's round-robins."""
    name: str
    max_velocity: float
    notes: dict[str, str | list[str]]


@dataclass
class Spec:
    group: str                       # 'melodic' | 'bass' | 'piano'
    inst: str                        # sample dir name (matches the app's voice id)
    base_url: str                    # source root; note paths are appended
    license: str                     # for the log + DATA_LICENSES.md
    layers: list[Layer] = field(default_factory=list)
    max_tail_s: float = MAX_TAIL_S   # per-instrument cap: pizz decays fast, pads ring


def notes_map(template: str, source_notes: list[str], shift: int,
              rr_tokens: list[str] | None = None) -> dict[str, str | list[str]]:
    """{output note name → source file(s)} for one layer.

    `template` is formatted with `note` (the SOURCE spelling), `midi` (its MIDI
    number, which some libraries put in the filename) and, when `rr_tokens` is
    given, `rr`. Output keys are the source note shifted by `shift` semitones —
    see the module docstring on why that shift exists."""
    out: dict[str, str | list[str]] = {}
    for note in source_notes:
        midi = to_midi(note)
        key = to_name(midi + shift)
        # The template builds a URL, so the source spelling has to be escaped:
        # a sharp-named file ("C#2") would otherwise read as a fragment and 404.
        esc = urllib.parse.quote(note, safe="")
        if rr_tokens:
            out[key] = [template.format(note=esc, midi=midi, rr=rr) for rr in rr_tokens]
        else:
            out[key] = template.format(note=esc, midi=midi)
    return out


# ── Instrument specs ─────────────────────────────────────────────────────────
# Every voice id below matches a frontend sample dir (frontend/public/samples/
# <group>/<inst>/) and an instrument-registry `playback_voice`. Voices with no
# entry here synthesize; see the "still synth-only" note at the bottom.

_VCSL = "https://raw.githubusercontent.com/sgossner/VCSL/master/"
_VSCO = "https://raw.githubusercontent.com/sgossner/VSCO-2-CE/master/"
_SFZI = "https://raw.githubusercontent.com/sfzinstruments/"

_CC0_VCSL = "VCSL (Versilian Community Sample Library) — CC0 / public domain"
_CC0_VSCO = "VSCO 2 Community Edition (Versilian Studios) — CC0 / public domain"
_CC0_KARO = "Karoryfer Samples (D. Smolken) — CC0 / public domain"
_CC0_DSMO = "D. Smolken — Otto Rubner double bass — CC0 / public domain"
_CCBY_GS = "Greg Sullivan E-Pianos — CC BY 3.0 (attribution in DATA_LICENSES.md)"

# Vibraphone: VCSL names middle C as C3, so its files sound an octave above their
# label. At +12 the set lands on F3–E6, exactly the registry's vibraphone range.
_VIB_NOTES = ["F2", "A2", "C3", "E3", "G3", "B3", "D4", "F4", "A4", "C5", "E5"]

# Electric bass (fingered): a Squier Jazz Bass, 4 dynamics × 4 round-robins.
_GROWL_NOTES = ["db2", "e2", "gb2", "a2", "c3", "eb3", "gb3", "a3", "c4", "eb4",
                "gb4", "a4", "c5", "eb5"]
# Picked bass: Squier Bass VI, flatwounds, bridge pickup ("linguine" set).
_LING_NOTES = ["db2", "e2", "g2", "bb2", "db3", "e3", "g3", "bb3", "db4", "e4",
               "g4", "bb4", "db5"]
# Fretless stand-in: dead flatwounds, neck pickup — the mellowest bass available.
_SWAG_NOTES = ["a1", "c2", "eb2", "gb2", "a2", "c3", "eb3", "gb3", "a3", "c4",
               "eb4", "gb4", "a4"]
# Upright: 1958 Otto Rubner double bass, pizzicato. Already at sounding pitch.
_UPRIGHT_NOTES = ["c1", "eb1", "g1", "bb1", "d2", "f2", "a2", "c3", "e3", "g3", "a3"]

SPECS: dict[str, Spec] = {
    # ── Mallets ───────────────────────────────────────────────────────────────
    "vibraphone": Spec(
        group="melodic", inst="vibraphone", base_url=_VCSL, license=_CC0_VCSL,
        layers=[
            # Soft mallets for gentle playing; hard mallets when struck hard. The
            # timbre — not just the level — changes with velocity.
            Layer("soft", 0.5, notes_map(
                "Idiophones/Struck%20Idiophones/Vibraphone/Soft%20Mallets/Vibes_soft_{note}_v2_rr1_Main.wav",
                _VIB_NOTES, shift=12)),
            Layer("hard", 1.0, notes_map(
                "Idiophones/Struck%20Idiophones/Vibraphone/Hard%20Mallets/Vibes_hard_{note}_v3_rr1_Main.wav",
                _VIB_NOTES, shift=12)),
        ],
    ),

    # ── Basses ────────────────────────────────────────────────────────────────
    "electric_bass_finger": Spec(
        group="bass", inst="electric_bass_finger",
        base_url=_SFZI + "karoryfer.growlybass/master/", license=_CC0_KARO,
        max_tail_s=3.5,
        layers=[
            Layer("pp", 0.30, notes_map("sustain/{note}_pp_rr1.wav", _GROWL_NOTES, shift=-12)),
            Layer("p", 0.55, notes_map("sustain/{note}_p_rr1.wav", _GROWL_NOTES, shift=-12)),
            Layer("f", 0.80, notes_map("sustain/{note}_f_rr1.wav", _GROWL_NOTES, shift=-12)),
            Layer("ff", 1.00, notes_map("sustain/{note}_ff_rr1.wav", _GROWL_NOTES, shift=-12)),
        ],
    ),
    "electric_bass_pick": Spec(
        group="bass", inst="electric_bass_pick",
        base_url=_SFZI + "karoryfer.pastabass/master/", license=_CC0_KARO,
        max_tail_s=3.5,
        layers=[
            Layer("vl1", 0.40, notes_map("samples/linguine/{note}_vl1_rr1.wav", _LING_NOTES, shift=-12)),
            Layer("vl2", 0.75, notes_map("samples/linguine/{note}_vl2_rr1.wav", _LING_NOTES, shift=-12)),
            Layer("vl3", 1.00, notes_map("samples/linguine/{note}_vl3_rr1.wav", _LING_NOTES, shift=-12)),
        ],
    ),
    "fretless_bass": Spec(
        group="bass", inst="fretless_bass",
        base_url=_SFZI + "karoryfer.swagbass/master/", license=_CC0_KARO,
        max_tail_s=3.5,
        layers=[
            Layer("p", 0.45, notes_map("notes/{note}_p_rr1.wav", _SWAG_NOTES, shift=-12)),
            Layer("f", 0.80, notes_map("notes/{note}_f_rr1.wav", _SWAG_NOTES, shift=-12)),
            Layer("fff", 1.00, notes_map("notes/{note}_fff_rr1.wav", _SWAG_NOTES, shift=-12)),
        ],
    ),
    "acoustic_bass": Spec(
        group="bass", inst="acoustic_bass",
        base_url=_SFZI + "dsmolken.double-bass/master/", license=_CC0_DSMO,
        max_tail_s=2.5,
        layers=[
            # Pizzicato decays fast and repeats constantly in a walking line, so
            # this is the one set worth spending round-robins on.
            Layer("p", 0.45, notes_map("pizz/pizz_{note}_p{rr}.wav", _UPRIGHT_NOTES,
                                       shift=0, rr_tokens=["a", "b"])),
            Layer("m", 0.75, notes_map("pizz/pizz_{note}_m{rr}.wav", _UPRIGHT_NOTES,
                                       shift=0, rr_tokens=["a", "b"])),
            Layer("f", 1.00, notes_map("pizz/pizz_{note}_f{rr}.wav", _UPRIGHT_NOTES,
                                       shift=0, rr_tokens=["a", "b"])),
        ],
    ),

    # ── Electric pianos ───────────────────────────────────────────────────────
    # electric_piano_2 is the Wurlitzer voice and this IS a Wurlitzer EP200.
    # Its dynamics are sampled unevenly, so each layer carries its own note list
    # (a layer needn't cover the same notes — Tone stretches the nearest zone).
    "electric_piano_2": Spec(
        group="melodic", inst="electric_piano_2",
        base_url=_SFZI + "GregSullivan.E-Pianos/master/Wurlitzer%20EP200/Samples/",
        license=_CCBY_GS, max_tail_s=5.0,
        layers=[
            Layer("mp", 0.45, notes_map("{note}mp.flac", [
                "a1", "e2", "a2", "eb3", "ab3", "db4", "gb4", "b4", "db5", "g5", "db6", "ab6"], shift=0)),
            Layer("f", 0.78, notes_map("{note}f.flac", [
                "a1", "c2", "f2", "b2", "e3", "ab3", "db4", "ab4", "db5", "g5", "db6", "ab6"], shift=0)),
            Layer("ff", 1.00, notes_map("{note}ff.flac", [
                "a1", "c2", "f2", "b2", "e3", "ab3", "db4", "e4", "g4", "db5", "g5"], shift=0)),
        ],
    ),
    # electric_piano_1 is the Rhodes voice. No Rhodes exists under a license we
    # can redistribute (jRhodes3 is CC BY-NC), so this is a Hohner Pianet T — the
    # nearest real vintage EP that is CC-BY. Same substitute-the-nearest-sampled-
    # instrument precedent as marimba → vibraphone in the registry.
    "electric_piano_1": Spec(
        group="melodic", inst="electric_piano_1",
        base_url=_SFZI + "GregSullivan.E-Pianos/master/Pianet%20T/Samples/",
        license=_CCBY_GS, max_tail_s=5.0,
        layers=[
            # This library prefixes each file with the note's MIDI number.
            Layer("p", 0.50, notes_map("{midi}_{note}_P.flac", [
                "F1", "A1", "C#2", "F2", "A2", "C#3", "E3", "A3",
                "C#4", "F4", "A4", "C#5", "F5", "A5", "C#6", "E6",
            ], shift=0)),
            Layer("ff", 1.00, notes_map("{midi}_{note}_FF.flac", [
                "F1", "A1", "C#2", "F2", "A2", "B2", "C#3", "F3",
                "A3", "C#4", "F4", "A4", "C#5", "F5", "A5", "C#6", "E6",
            ], shift=0)),
        ],
    ),

    # ── Strings ───────────────────────────────────────────────────────────────
    # A real section stacks by register, so this one does too: cellos hold the
    # bottom, violas the middle, violins the top. VSCO also names middle C as C3,
    # hence shift=+12 (verified against each section's real fundamental).
    "string_ensemble_1": Spec(
        group="melodic", inst="string_ensemble_1", base_url=_VSCO, license=_CC0_VSCO,
        max_tail_s=6.0,
        layers=[
            Layer("soft", 0.55, {
                **notes_map("Strings/Cello%20Section/susvib/susvib_{note}_v1_1.wav",
                            ["C1", "E1", "G1", "B1", "D2"], shift=12),
                **notes_map("Strings/Viola%20Section/susvib/ViolaEns_susvib_{note}_v1_1.wav",
                            ["E2", "G2", "B2", "D3"], shift=12),
                **notes_map("Strings/Violin%20Section/susVib/VlnEns_susVib_{note}_v1.wav",
                            ["F#3", "A3", "C4", "E4", "G4", "B4", "D5"], shift=12),
            }),
            Layer("loud", 1.00, {
                **notes_map("Strings/Cello%20Section/susvib/susvib_{note}_v3_1.wav",
                            ["C1", "E1", "G1", "B1", "D2"], shift=12),
                **notes_map("Strings/Viola%20Section/susvib/ViolaEns_susvib_{note}_v2_1.wav",
                            ["E2", "G2", "B2", "D3"], shift=12),
                **notes_map("Strings/Violin%20Section/susVib/VlnEns_susVib_{note}_v2.wav",
                            ["F#3", "A3", "C4", "E4", "G4", "B4", "D5"], shift=12),
            }),
        ],
    ),
}

# Still synth-only, for lack of a redistributable source (checked July 2026):
#   clavinet, drawbar_organ, accordion, acoustic_guitar_nylon — no CC0/CC-BY
#     multisample of a Clavinet, Hammond/drawbar organ, accordion or nylon-string
#     guitar was found. VCSL's organs are pipe organs; the CC0 guitar libraries
#     are all electric.
#   synth_bass_1 — intentionally synthesized: it IS a synth, and the app's own
#     oscillator is more honest (and tweakable) than a frozen sample of one.
#   slap_bass_1 — aliased to electric_bass_finger in the frontend rather than
#     given its own set; no CC0 slap library exists.


def db_to_amp(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def fetch(url: str) -> Path:
    """Download to the cache (skip if present); return the local path."""
    key = urllib.parse.quote(url, safe="")
    dest = CACHE / key
    if dest.exists():
        return dest
    CACHE.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)
    return dest


def load_trimmed(src: Path, max_tail_s: float) -> tuple[np.ndarray, int]:
    """Decode (WAV/FLAC) → mono, silence-trimmed, tail-capped float array."""
    data, sr = sf.read(str(src), always_2d=True)
    mono = data.mean(axis=1)

    # Trim leading/trailing near-silence, keeping a short tail.
    thr = db_to_amp(TRIM_THRESHOLD_DB)
    loud = np.where(np.abs(mono) > thr)[0]
    if len(loud):
        start = loud[0]
        end = min(len(mono), loud[-1] + int(TAIL_PAD_S * sr))
        mono = mono[start:end]
    return mono[: int(max_tail_s * sr)], int(sr)


def encode_mp3(mono: np.ndarray, sr: int, gain: float, dst: Path) -> int:
    """Apply `gain`, encode to mono MP3, write. Returns output byte size."""
    pcm = (np.clip(mono * gain, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    enc = lameenc.Encoder()
    enc.set_bit_rate(MP3_BITRATE)
    enc.set_in_sample_rate(sr)
    enc.set_channels(1)
    enc.set_quality(2)
    mp3 = enc.encode(pcm) + enc.flush()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(mp3)
    return len(mp3)


def build(spec: Spec) -> None:
    out_dir = SAMPLES_DIR / spec.group / spec.inst
    print(f"\n=== {spec.inst} ({spec.group}) ===\n  source: {spec.license}")

    # Pass 1 — decode everything, remembering which note each sample belongs to.
    # Gain is then computed PER NOTE rather than per file, so a soft layer stays
    # softer than a hard one: normalising each file on its own would flatten the
    # very dynamic difference the velocity layers exist to capture.
    decoded: list[tuple[str, str, np.ndarray, int, Path]] = []   # note, out_rel, audio, sr, dst
    manifest_layers: list[dict] = []

    for layer in spec.layers:
        urls: dict[str, str | list[str]] = {}
        for note, rel in layer.notes.items():
            rels = rel if isinstance(rel, list) else [rel]
            out_rels: list[str] = []
            for i, r in enumerate(rels):
                suffix = f"_rr{i + 1}" if len(rels) > 1 else ""
                out_rel = f"{layer.name}/{note}{suffix}.mp3"
                audio, sr = load_trimmed(fetch(spec.base_url + r), spec.max_tail_s)
                decoded.append((note, out_rel, audio, sr, out_dir / out_rel))
                out_rels.append(out_rel)
            urls[note] = out_rels if len(out_rels) > 1 else out_rels[0]
        manifest_layers.append({"maxVelocity": layer.max_velocity, "urls": urls})

    # Pass 2 — one gain per note, taken from that note's loudest layer.
    peaks: dict[str, float] = {}
    for note, _, audio, _, _ in decoded:
        peaks[note] = max(peaks.get(note, 0.0), float(np.max(np.abs(audio))))
    target = db_to_amp(PEAK_DB)

    total = 0
    for note, out_rel, audio, sr, dst in decoded:
        size = encode_mp3(audio, sr, target / (peaks[note] or 1.0), dst)
        total += size
        print(f"  ok    {out_rel}  ({size // 1024} KB)")

    (out_dir / "velocity.json").write_text(json.dumps({"layers": manifest_layers}, indent=2) + "\n")

    # Drop anything the manifest no longer references — otherwise a spec change
    # (a dropped note, a corrected octave) leaves orphaned MP3s that ship in the
    # build forever. Only ever touches .mp3 files under this instrument's dir.
    keep = {out_dir / rel for _, rel, _, _, _ in decoded}
    for stale in sorted(out_dir.rglob("*.mp3")):
        if stale not in keep:
            stale.unlink()
            print(f"  prune {stale.relative_to(out_dir)}")
    for empty in sorted(out_dir.glob("*/"), reverse=True):
        if empty.is_dir() and not any(empty.iterdir()):
            empty.rmdir()

    print(f"  wrote velocity.json — {len(spec.layers)} layers, "
          f"{len(decoded)} samples, {total // 1024} KB total")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build velocity-layered sample sets.")
    ap.add_argument("instruments", nargs="*", help="specific instruments (default: all)")
    ap.add_argument("--list", action="store_true", help="list available specs and exit")
    args = ap.parse_args()

    if args.list:
        for name, spec in SPECS.items():
            print(f"{name:24} {spec.group:8} {spec.license}")
        return

    names = args.instruments or list(SPECS)
    unknown = [n for n in names if n not in SPECS]
    if unknown:
        print(f"Unknown instrument(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Available: {', '.join(SPECS)}", file=sys.stderr)
        sys.exit(1)

    for name in names:
        build(SPECS[name])
    print("\nDone. Re-run the app; upgraded instruments now load velocity layers.")


if __name__ == "__main__":
    main()
