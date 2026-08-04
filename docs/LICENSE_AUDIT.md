# License compliance audit — 2026-07-23

A full pass over everything GenreGrid ships, to confirm we (a) respect third-party
licenses and (b) correctly assert our own (GPL-3.0). Companion to
[`DATA_LICENSES.md`](../DATA_LICENSES.md), which covers mined corpora and priors.

**Scope:** bundled audio samples, frontend (npm) and backend (pip) dependencies,
fonts/icons, and our own license declaration + source headers.

---

## Verdict

| Area | Status |
|---|---|
| Our license declaration (GPL-3.0) | ✅ after fixing one metadata mismatch |
| Frontend npm dependencies | ✅ all GPL-3.0-compatible |
| Backend pip dependencies | ✅ all GPL-3.0-compatible |
| Fonts | ✅ none bundled (system font stacks) |
| Icons | ✅ first-party |
| Piano samples | ✅ Salamander, CC-BY 3.0 (attributed) |
| Vibraphone samples | ✅ VCSL, CC0 |
| **Drum samples** | ✅ unconfirmed license + **unused** — deleted |
| **Bass + melodic samples** | ✅ MusyngKite removed; 7 of those voices re-sourced from CC0/CC-BY libraries (§6) |

**Result: the app ships no asset with unconfirmed redistribution rights.** Sampled
voices are piano (CC-BY 3.0), vibraphone + 4 basses + string ensemble (CC0), and two
electric pianos (CC-BY 3.0). Everything else synthesizes, toggleable via the transport
bar's Samples / Synth control.

---

## 1. Our own license (GPL-3.0)

- `LICENSE` at repo root is the full GPL-3.0 text. ✅
- Every frontend `src/**/*.{ts,vue}` and backend `backend/app/**/*.py` file carries the
  GPL header granting "version 3 … or (at your option) any later version." Only empty
  `__init__.py` package markers lack it (no copyrightable content). ✅
- **Mismatch (fixed):** `frontend/package.json` declared `"license": "GPL-3.0-only"`, but
  the source headers grant **or-later**. Corrected to `GPL-3.0-or-later` so the metadata
  matches the actual grant. The backend has no package metadata license field to set.

## 2. Frontend dependencies (npm)

49 production dependencies, by license: MIT (39), ISC (3), BSD-2-Clause (1),
BSD-3-Clause (1), Apache-2.0 (1), 0BSD (1), BlueOak-1.0.0 (1), Python-2.0 (1). All are
permissive and **GPL-3.0-compatible**. The only `UNLICENSED` entry is our own root
package (`genregrid-frontend`), not a third party.

Dev-only dependencies additionally include a few MPL-2.0 packages (build tooling); MPL-2.0
is GPL-compatible and, regardless, dev tooling is **not distributed** in the packaged app.

_Re-check: `cd frontend && npx license-checker-rseidelsohn --production --summary`._

## 3. Backend dependencies (pip)

fastapi, starlette, httpx (BSD-3), pydantic, mido, uvicorn, python-multipart, idna,
pytest, pytest-asyncio (MIT/BSD). All permissive and **GPL-3.0-compatible**.

## 4. Fonts & icons

- **Fonts:** none bundled — the UI uses system font stacks, so nothing to license. ✅
- **Icons:** `frontend/public/icon.{png,ico}` are first-party GenreGrid artwork. ✅

## 5. Bundled audio samples

Samples are **data**, licensed separately from the GPL code. Detail in
[`DATA_LICENSES.md`](../DATA_LICENSES.md → "Bundled instrument samples").

- ✅ **Piano** — Salamander Grand Piano, **CC-BY 3.0**, attributed.
- ✅ **Vibraphone** — **VCSL, CC0**, velocity-layered (migrated 2026-07-23).
- ✅ **Drums** (`samples/drums/`, 8 kits) — from Tone.js `audio` repo, which has **no
  LICENSE file** (unconfirmed rights on vintage drum-machine samples). The app plays a
  **synthesized** kit (`makeSynthKit`); `getDrumKit`/the sampled kits had **no callers**.
  **Deleted** (dead weight — zero sound impact), along with the dead code.
- ✅ **Bass** (6 sets) **+ Melodic** (7 sets: electric pianos, clavinet, accordion, drawbar
  organ, nylon guitar, string ensemble) — from gleitz `midi-js-soundfonts` → **MusyngKite**.
  The redistributor labels it CC-BY-SA 3.0, but the soundfont's original author states it is
  "free to use but **not meant to be redistributed** … or used for commercial purposes" —
  so our redistribution rights are **not confirmed**. **Deleted; those voices now synthesize.**

### How the MusyngKite removal was done

Goal: ship **no** MusyngKite-derived audio, achieved as follows:

1. Deleted all MusyngKite sample sets. Sampled voices are gated behind confirmed-license
   allowlists (`SAMPLED_VOICES`, `SAMPLED_BASS_VOICES`); voices not on them synthesize.
2. Added a **Samples / Synth toggle** (`sampleMode`, persisted) so users can A/B the sampled
   voices against full synthesis — and the seam a future "bring your own samples" feature uses.
3. Removed `scripts/download_samples.py` (it only fetched the now-banned sources).

**Sources considered and rejected for re-sourcing:**
- **University of Iowa MIS** — widely called "free," but the site carries **no explicit
  license grant** (same ambiguity as MusyngKite), so it is *not* used.
- **Freesound** — many CC0 samples exist, but the API requires auth unavailable in the
  automation environment; a manual, per-sample CC0 curation pass remains a future option.

---

## 6. Re-sourcing the removed voices (2026-07-23, follow-up)

The MusyngKite removal left 13 voices synthesizing. Seven have since been restored from
libraries with **explicit, verifiable** license files, all fetched by
`scripts/build_velocity_samples.py`:

| Voice | Source | License |
|---|---|---|
| `electric_bass_finger` (+ `slap_bass_1`) | Karoryfer **Growlybass** (Squier Jazz Bass) | CC0 |
| `electric_bass_pick` | Karoryfer **Pastabass** ("linguine": flatwound, picked) | CC0 |
| `fretless_bass` | Karoryfer **Swagbass** (dead flatwounds, neck pickup) | CC0 |
| `acoustic_bass` | D. Smolken **Otto Rubner double bass**, pizzicato | CC0 |
| `electric_piano_2` | Greg Sullivan **Wurlitzer EP200** | CC-BY 3.0 |
| `electric_piano_1` | Greg Sullivan **Hohner Pianet T** (stands in for a Rhodes) | CC-BY 3.0 |
| `string_ensemble_1` | **VSCO 2 CE** cello/viola/violin sections | CC0 |

The [`sfzinstruments`](https://github.com/sfzinstruments) GitHub organisation was the
find that unblocked this: it hosts dozens of sample libraries each with a machine-readable
SPDX license, so CC0 sets can be identified without guesswork. Licenses were confirmed by
reading each repository's `LICENSE` file, not the GitHub badge alone.

**Rejected during this pass:** **jRhodes3** — the best-sounding free Rhodes, and exactly
the voice we most wanted — is **CC BY-NC 4.0**. NonCommercial is incompatible with shipping
here, so `electric_piano_1` uses the Pianet T instead.

**Still synthesized, no clean source found:** clavinet. (`synth_bass_1` is synthesized
deliberately — it is a synth.)

---

## 7. Re-sourcing the remaining three voices (2026-08-04)

Drawbar organ, accordion, and nylon guitar — all three still-synthesized voices from
§6 that weren't a synth by choice — are re-sourced from the
[FreePats](https://freepats.zenvoid.org/) project, found by checking for new CC0
releases since the original 2026-07-23 pass rather than re-trying the same rejected
sources. Each page's license statement was read directly (not just an aggregator
badge), matching this audit's standard:

| Voice | Source | License |
|---|---|---|
| `drawbar_organ` | FreePats — Drawbar Organ Emulation (Roberto, recorded from the setBfree software organ) | CC0 1.0 |
| `accordion` | FreePats — Button Accordion HN (samples: Jeff Stauffer; sound bank: michael02022) | CC0 1.0 |
| `acoustic_guitar_nylon` | FreePats — Spanish Classical Guitar (Roberto) | CC0 1.0 |

Each source ships as a single archive (`.tar.xz` / `.7z`) rather than one URL per
note, so `scripts/build_velocity_samples.py` gained a `fetch_archive()` step
(download once, extract, address the extracted files through the same
base-URL-plus-template machinery via a `file://` URI) — no change to the per-note
fetch/normalise/encode pipeline itself.

**Pitch verified two ways, not just trusted from the filename**, per this audit's own
rule: each source SFZ's own `pitch_keycenter` opcode was read directly (not inferred
from the filename), then spot-checked against the actual audio by autocorrelation
pitch estimation. Two of three sources use the raw filename as the real pitch
(`shift=0`); the accordion set's filenames are one octave above sounding pitch
(its own SFZ maps `"C5.wav"` to `pitch_keycenter=60`, i.e. real C4) — the same
octave-naming trap this audit already flags for VCSL/VSCO, applied here via `shift=-12`
rather than by chance.

**Not applicable to these three:** they're one-shot/sustained recordings with no
per-note dynamics in the source (an organ's timbre doesn't change with key velocity,
only its drawbar registration; the accordion and guitar sets are single-dynamic too),
so each ships as one velocity layer rather than the multi-layer sets §6's voices got.

**Clavinet remains unsourced.** FreePats lists one as "in development" (not yet
released); the only other clavinet SFZ found (musical-artifacts.com) carries an
unconfirmed/unknown license, so it fails this audit's bar the same way the University
of Iowa MIS source did in §5.

---

## Maintenance

Re-run this audit when adding any dependency, sample set, font, or icon. Never bundle audio
without a confirmed CC0 / public-domain / CC-BY (with attribution) license. Keep the repo
free of any asset whose redistribution rights are unconfirmed.
