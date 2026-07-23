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

SOURCES & LICENSING. Each spec names its source and license. Only CC0 / public-
domain sources are wired in here so the produced MP3s can ship with the GPL code
(samples are data, licensed separately — see DATA_LICENSES.md). VCSL is CC0. Do
not add a source here without confirming its license permits redistribution.
"""
from __future__ import annotations

import argparse
import json
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
CACHE = REPO / ".sample-cache"          # downloaded source WAVs (git-ignored)

# ── Conversion settings ──────────────────────────────────────────────────────
TRIM_THRESHOLD_DB = -45.0   # trim leading/trailing audio quieter than this
TAIL_PAD_S = 0.15           # keep this much tail after the last loud sample
PEAK_DB = -1.0              # normalise each sample to this peak
MAX_TAIL_S = 6.0            # cap very long rings so files stay small
MP3_BITRATE = 128


@dataclass
class Layer:
    """One velocity layer: an inclusive upper velocity bound (0..1) and the source
    WAV (relative to the spec's base URL) for each note. A list gives round-robins."""
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


# ── Instrument specs ─────────────────────────────────────────────────────────
# NOTE: VCSL (CC0) is an acoustic/orchestral library. It cleanly covers only a few
# of GenreGrid's voices (vibraphone here; grand piano, marimba, upright exist too).
# The electric/synth voices (Rhodes, clavinet, electric/synth bass, …) are NOT in
# any single CC0 library and are intentionally absent — they keep their legacy
# single-layer sets until a license-clean multi-velocity source is sourced.

_VIB = "https://raw.githubusercontent.com/sgossner/VCSL/master/Idiophones/Struck%20Idiophones/Vibraphone/"
_VIB_NOTES = ["C3", "E3", "G3", "B3", "D4", "F4", "A4", "C5", "E5"]

SPECS: dict[str, Spec] = {
    "vibraphone": Spec(
        group="melodic",
        inst="vibraphone",
        base_url=_VIB,
        license="VCSL (Versilian Community Sample Library) — CC0 / public domain",
        layers=[
            # Soft mallets for gentle playing; hard mallets when struck hard. The
            # timbre — not just the level — changes with velocity.
            Layer("soft", 0.5, {n: f"Soft%20Mallets/Vibes_soft_{n}_v2_rr1_Main.wav" for n in _VIB_NOTES}),
            Layer("hard", 1.0, {n: f"Hard%20Mallets/Vibes_hard_{n}_v3_rr1_Main.wav" for n in _VIB_NOTES}),
        ],
    ),
}


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


def convert(src: Path, dst: Path) -> int:
    """WAV → trimmed, peak-normalised mono MP3. Returns output byte size."""
    data, sr = sf.read(str(src), always_2d=True)
    mono = data.mean(axis=1)

    # Trim leading/trailing near-silence, keeping a short tail.
    thr = db_to_amp(TRIM_THRESHOLD_DB)
    loud = np.where(np.abs(mono) > thr)[0]
    if len(loud):
        start = loud[0]
        end = min(len(mono), loud[-1] + int(TAIL_PAD_S * sr))
        mono = mono[start:end]
    mono = mono[: int(MAX_TAIL_S * sr)]

    # Peak-normalise.
    peak = float(np.max(np.abs(mono))) or 1.0
    mono = mono * (db_to_amp(PEAK_DB) / peak)

    pcm = (np.clip(mono, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    enc = lameenc.Encoder()
    enc.set_bit_rate(MP3_BITRATE)
    enc.set_in_sample_rate(int(sr))
    enc.set_channels(1)
    enc.set_quality(2)
    mp3 = enc.encode(pcm) + enc.flush()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(mp3)
    return len(mp3)


def build(spec: Spec) -> None:
    out_dir = SAMPLES_DIR / spec.group / spec.inst
    print(f"\n=== {spec.inst} ({spec.group}) ===\n  source: {spec.license}")
    manifest_layers = []
    total = 0

    for layer in spec.layers:
        urls: dict[str, str | list[str]] = {}
        for note, rel in layer.notes.items():
            rels = rel if isinstance(rel, list) else [rel]
            out_rels: list[str] = []
            for i, r in enumerate(rels):
                src = fetch(spec.base_url + r)
                suffix = f"_rr{i + 1}" if len(rels) > 1 else ""
                out_name = f"{note}{suffix}.mp3"
                size = convert(src, out_dir / layer.name / out_name)
                total += size
                out_rels.append(f"{layer.name}/{out_name}")
                print(f"  ok    {layer.name}/{out_name}  ({size // 1024} KB)")
            urls[note] = out_rels if len(out_rels) > 1 else out_rels[0]
        manifest_layers.append({"maxVelocity": layer.max_velocity, "urls": urls})

    manifest = {"layers": manifest_layers}
    (out_dir / "velocity.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"  wrote velocity.json — {len(spec.layers)} layers, {total // 1024} KB total")


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
