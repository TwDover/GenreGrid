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
| **Bass + melodic samples** | ✅ MusyngKite removed — those voices now synthesize |

**Result: the app ships no asset with unconfirmed redistribution rights.** Remaining
sampled voices are piano (CC-BY 3.0) and vibraphone (CC0); everything else synthesizes,
toggleable via the transport bar's Samples / Synth control.

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

Confirmed-clean, direct-download sources that *were* usable: **VCSL (CC0)** and **Salamander
(CC-BY)** — which only cover piano + vibraphone among GenreGrid's voices.

---

## Maintenance

Re-run this audit when adding any dependency, sample set, font, or icon. Never bundle audio
without a confirmed CC0 / public-domain / CC-BY (with attribution) license. Keep the repo
free of any asset whose redistribution rights are unconfirmed.
