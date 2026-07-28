# GenreGrid Roadmap

A living, prioritized roadmap from the July 2026 project survey. Check items off as
they land; add new findings under the right phase so nothing gets lost.

**Status legend:** `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` won't do / obsolete ·
`[→]` moved to another phase

_Last updated: 2026-07-23 — Phase 1 complete. Phase 2 complete except for desktop runtime
testing of the custom-instruments MVP: limiter, per-style FX, loudness norm, velocity-layer
engine, license compliance, and the sample re-sourcing pass have all landed._

---

## Health snapshot (at survey time)

- Backend: ~14.3k LoC Python, **132 tests passing**, ruff gate (E/F/W) configured.
- Frontend: ~11.3k LoC TS/Vue, **12 tests** (3 files) — thin coverage.
- Electron: `contextIsolation: true`, `nodeIntegration: false` — securely configured.
- Overall: a well-built project. Items below are refinements, not firefighting.

---

## Phase 1 — Harden (high value, low risk)

- [x] **Path traversal in `download_export`** — hardened all three export routes with a
  containment check (`_safe_export_dir` + `is_relative_to`) and a strict id pattern; new
  regression test. → `backend/app/api/routes_generate.py`
- [x] **CORS `*` in the packaged app** — replaced with a localhost/127.0.0.1 origin regex
  (covers the renderer's random port, blocks external sites at preflight). Electron no
  longer sets `CORS_ORIGINS: '*'`. → `backend/app/main.py`, `frontend/electron/main.ts`
  - [ ] _Optional follow-up:_ per-session token as defense-in-depth on mutating JSON
    endpoints. Deferred — a header token complicates file-URL/audio loading; the origin
    allowlist already closes the browser-based attack.
- [x] **`will-navigate` / `setWindowOpenHandler` guards** added — in-app navigation is
  same-origin only; external links open in the OS browser. → `frontend/electron/main.ts`
- [x] **`save-temp-file` IPC** now `path.basename()`s the renderer-supplied filename.
  → `frontend/electron/main.ts`
- [x] **`create_custom_style`** now validates via `CustomStyleRequest` (typed core fields
  + bounds, `extra="allow"` for rich style config). → `backend/app/models/schemas.py`
- [x] **Bundle the Salamander piano samples locally** — the 30-file sample set now lives
  in `frontend/public/samples/piano/` (2 MB) and `loader.ts` loads `/samples/piano/`, so
  the flagship piano works fully offline and no longer fetches from `tonejs.github.io`.
  Attribution (CC-BY 3.0, Alexander Holm) added to `DATA_LICENSES.md`.
  → `frontend/src/soundfonts/loader.ts`

## Phase 2 — Sound polish

- [x] **Master bus glue/limiting** — added a Linux-safe soft-clip limiter on the master:
  a `WaveShaper` (static transfer curve, not a `DynamicsCompressor` — that renders silence
  on Linux Electron) that's transparent below −4.4 dBFS, bends through a gentle quadratic
  knee, and holds peaks under a −0.13 dBFS ceiling. Wired into all three master paths (live
  `masterOut → limiter → dest`, offline WAV render, and the live MediaRecorder tap now reads
  post-limiter). New pure-math unit tests cover the transfer curve.
  → `frontend/src/soundfonts/loader.ts` (`makeMasterLimiter`), `useMidiPlayer.ts`
- [x] **Velocity layers / round-robins in sample sets** — Built `LayeredSampler`
  (`layeredSampler.ts`): a drop-in over `Tone.Sampler` that plays a different sample per
  velocity range (real dynamics, not just gain) + cycles round-robins, driven by a per-instrument
  `velocity.json` manifest. Backward-compatible; wired into the piano/bass/melodic loaders (offline
  WAV path is synth-only, untouched). Reproducible pipeline (`scripts/build_velocity_samples.py`,
  `soundfile`+`lameenc`) fetches CC0/CC-BY WAV/FLAC → trimmed mono mp3 + manifest. **8 instruments**
  now ship layered (vibraphone, 4 basses, 2 electric pianos, string ensemble) — see the re-sourcing
  item below.
  → `frontend/src/soundfonts/layeredSampler.ts`, `scripts/build_velocity_samples.py`
- [x] **License compliance pass** (added scope) — full audit (`docs/LICENSE_AUDIT.md`) of samples,
  npm + pip deps, fonts/icons, and our own GPL declaration. Findings/fixes: deps all
  GPL-3.0-compatible; fixed `package.json` `GPL-3.0-only`→`-or-later` to match the source headers;
  **removed all MusyngKite-derived samples** (ambiguous license) and the unused/unlicensed Tone.js
  drum samples. Those voices now synthesize. Added a **Samples / Synth toggle** (`sampleMode`,
  persisted) in the transport bar to A/B sampled vs synth — the seam a future "bring your own
  samples" feature plugs into. Net: the app ships no asset with unconfirmed redistribution rights.
- [x] **Loudness normalization across styles** — per-family master trim (`MASTER_TRIM_DB`)
  applied on the pre-limiter master when a style starts, so perceived volume doesn't jump
  between genres (hot electronic mixes pulled down, sustained pads nudged up). Ramped, not
  stepped. A true per-style LUFS target would need offline measurement; these are hand-tunable
  starting points. → `frontend/src/soundfonts/fxPresets.ts`, `loader.ts` (`setMasterTrimDb`)
- [x] **Per-style FX presets** — the shared melodic-bus chorus/delay + reverb are retuned
  per style family (`MELODIC_FX_PRESETS`) instead of being fixed: ambient/cinematic get a long
  lush tail, electronic more movement, trap/drill tight & dry, lo-fi wobbly. Applied live by
  mutating the shared nodes' params; the reverb IR is only regenerated when decay changes.
  → `frontend/src/soundfonts/fxPresets.ts`, `loader.ts` (`applyMelodicFxPreset`)
- [x] **Re-source clean samples for the synth-only voices** — _unblocked; 7 of 13 restored._
  The [`sfzinstruments`](https://github.com/sfzinstruments) GitHub org was the find: dozens of
  sample libraries with machine-readable SPDX licenses, so CC0 sets can be identified without
  guesswork. Restored, all velocity-layered via `scripts/build_velocity_samples.py`:
  **all 4 acoustic/electric basses** (Karoryfer Growlybass / Pastabass / Swagbass + Smolken's
  double bass, CC0 — `slap_bass_1` aliases to the fingered set), **both electric pianos**
  (Greg Sullivan Wurlitzer EP200 + Pianet T, CC-BY 3.0), and the **string ensemble**
  (VSCO 2 CE cello/viola/violin sections, CC0). Sample tree 3.4 MB → 20 MB.
  Script gained FLAC input, a per-spec octave `shift` (several libraries name files by
  *written* rather than sounding pitch — every one verified by measuring the fundamental),
  per-note gain (normalising each file separately was flattening the very dynamics the
  velocity layers exist for), and stale-output pruning.
  **Found and fixed en route:** the shipped vibraphone was mapped **an octave too low** (VCSL
  names middle C as C3). New `sampleManifests.test.ts` validates every shipped `velocity.json`
  — note names parse, referenced files exist, layers ascend to 1.0, and each set's pitch span
  sits in a tight window, so an octave slip fails the suite instead of someone's ears.
  Also repaired `test_playback_voices.py`, red since the license pass deleted `samples/bass/`.
  **Still synth-only (4):** clavinet, drawbar organ, accordion, nylon guitar — no CC0/CC-BY
  multisample found (VCSL's organs are pipe organs; the CC0 guitar libraries are all electric).
  `synth_bass_1` stays synthesized by choice. Rejected: **jRhodes3** is CC BY-**NC**, so the
  Rhodes voice uses a Hohner Pianet T instead. → `docs/LICENSE_AUDIT.md` §6, `DATA_LICENSES.md`
- [~] **User-uploaded custom instruments** (SF2/samples) + per-part instrument picker
  _(promoted from Phase 4; MVP built, needs desktop runtime testing)_ — users add their own
  samples, mapped to notes/velocities, and pick which instrument plays **each** part; also
  sidesteps the licensing gap above (user audio is theirs). Design + status in
  **[`custom-instruments-design.md`](custom-instruments-design.md)**. **Shipped (T1 one-shot +
  T2 note-named tiers):** pure mapping core (`customInstruments.ts`, +15 tests), library store
  (`useCustomInstruments.ts`), Electron storage IPC (`userData/instruments/`, played as blob:
  URLs — no custom scheme, avoids the Linux Web-Audio silence bug), per-part resolution in
  `useMidiPlayer.ts`, and the Instruments panel + 🎹 transport button.
  **Second pass** closed the three things that made the first cut confusing:
  (a) **`kind` was dead metadata** — collected, stored, displayed, read by nothing; it now
  selects the mapping shape and filters which instruments a part offers;
  (b) **drum kits now exist** — `drums` was missing from both the kind dropdown *and* the part
  resolution loop, so a kit could be neither added nor played. Kits are a separate shape
  (GM pitch → single-zone manifest, never pitch-shifted), import matches filenames to the
  twelve `DRUM_MAP` pieces and hands back anything it can't place instead of guessing, and
  unfilled pieces fall through to the synth kit so a two-file kit works immediately;
  (c) **the panel shows a style's real instrument lineup** with a this-style / all-styles scope
  toggle — per-style assignment was already fully supported by the store and resolver, the UI
  just never passed a `styleId`. A per-style "Built-in" now correctly beats the global default
  instead of silently inheriting it.
  The kit editor has a **per-slot audition** (`soundfonts/audition.ts`): ▶ plays the mapped
  sample, or the synth fallback when a slot is empty, so a mis-mapped file is caught where
  it's edited rather than on playback.
  **TODO:** runtime-test on desktop (import/assign/play/audition/edit-kit/delete), then
  multi-file kit slots, chromatic-instrument preview, SF2/SFZ import (T4), auto
  pitch-detection, web/OPFS storage.
  → `soundfonts/customInstruments.ts`, `soundfonts/customDrumKit.ts`, `soundfonts/audition.ts`, `composables/useCustomInstruments.ts`, `components/InstrumentsPanel.vue`, `electron/main.ts`

## Phase 3 — Performance & refactor

- [ ] **Parallelize full-song section generation** — song builds take ~1–2 min and
  sections generate serially though they're embarrassingly parallel. SSE progress
  plumbing (`generate-stream`) already exists.
  → `backend/app/api/routes_song.py`
- [ ] **Extract song/arrangement logic out of route god-files into `services/`** —
  handlers should be thin. → `routes_song.py` (1498), `routes_generate.py` (1299)
- [ ] **Split `useMidiPlayer.ts`** (1018 lines) into focused composables.
- [ ] **Log swallowed exceptions** — 27 broad/bare `except`; several return silently
  (e.g. `record_export_keep`). Add logging.
- [ ] **Grow frontend test coverage** — 12 tests vs 132 backend; the audio scheduler and
  WAV-render path (most fragile code) are untested.
- [ ] **Clear deprecation warnings** — Starlette `TestClient` httpx warning; Electron
  numeric-level `console-message` signature. → `frontend/electron/main.ts:206`

## Phase 4 — Features

- [ ] **Expose the data-driven priors toggle in the UI** — wired end-to-end already, no
  frontend control yet. Low effort.
- [ ] **Non-4/4 time signatures** (6/8, 3/4, 7/8) — currently hardcoded `numerator=4`.
  → `backend/app/services/midi_writer.py:162`
- [→] **Custom soundfont / SF2 upload** — _promoted to Phase 2 (Sound polish)._
- [ ] **Surface WAV/offline-audio export more prominently** — already implemented
  (OfflineAudioContext + render queue); just under-discovered.
- [ ] **Tempo automation & mid-song modulation** — partial today (`chorus_key_shift`).

---

## Done log

- **2026-07-23 — Phase 1 security hardening** (uncommitted working changes):
  - Export downloads hardened against path traversal (`_safe_export_dir` containment
    check on `/exports/{gen_id}/bundle.zip`, `/sections.zip`, and `/{filename}`).
  - CORS locked to a localhost-only origin regex; dropped the packaged `CORS_ORIGINS=*`.
  - Electron `will-navigate` + `setWindowOpenHandler` guards; `save-temp-file` basenames
    the filename.
  - `POST /styles/custom` validated with a `CustomStyleRequest` model.
  - Salamander piano bundled locally (`public/samples/piano/`, 2 MB) — flagship piano is
    now fully offline; CC-BY 3.0 attribution added to `DATA_LICENSES.md`.
  - Tests: +3 (traversal rejection, CORS allow/deny). Suite 131→134 green; ruff clean;
    frontend `vue-tsc` + vitest clean.

- **2026-07-23 — Phase 2 sound polish (in progress):**
  - Master soft-clip limiter added (Linux-safe `WaveShaper`, not a `DynamicsCompressor`):
    transparent below −4.4 dBFS, gentle quadratic knee, hard ceiling at −0.13 dBFS.
    Applied consistently across live playback, the offline WAV/stem render, and the live
    MediaRecorder export (which now taps the post-limiter node). Tests: +5 (transfer-curve
    math).
  - **Per-style FX presets** + **cross-style loudness normalization** landed. Shared melodic
    FX (chorus/delay/reverb) retuned per style family; pre-limiter master trimmed per family
    so genres sit at an even level. Applied when a style starts. Tests: +4.
  - **Velocity-layer / round-robin infrastructure** landed: `LayeredSampler`, a manifest-driven
    (`velocity.json`), backward-compatible drop-in for `Tone.Sampler`, wired into all three live
    sample loaders. Tests: +8. Reproducible sample pipeline added
    (`scripts/build_velocity_samples.py`). **Vibraphone** migrated to VCSL CC0 with soft/hard
    velocity layers (superseding the ambiguously-licensed MusyngKite set).
  - **License compliance pass** (`docs/LICENSE_AUDIT.md`): audited samples, npm/pip deps,
    fonts/icons, and our own GPL declaration. Deps all GPL-compatible. Fixed `package.json`
    license (`GPL-3.0-only`→`-or-later`). **Removed all MusyngKite samples** (ambiguous
    license) + unused/unlicensed Tone.js drum samples + dead `getDrumKit` code + the
    `download_samples.py` fetcher. Removed voices synthesize; added a persisted **Samples /
    Synth toggle** in the transport bar. Iowa MIS was evaluated and rejected (no explicit
    license). Net: no shipped asset has unconfirmed redistribution rights.
  - Frontend suite 12→29 green; `vue-tsc` + eslint + production build clean.

- **2026-07-23 — Phase 2 sample re-sourcing:**
  - Unblocked the "13 synth-only voices" item via the `sfzinstruments` GitHub org (SPDX-tagged
    sample libraries). **7 voices restored**, all velocity-layered: 4 basses (CC0), 2 electric
    pianos (CC-BY 3.0), string ensemble (CC0). `slap_bass_1` aliases to the fingered bass.
  - `build_velocity_samples.py` gained FLAC decoding, per-spec octave `shift` (verified by
    measuring each source's fundamental — several libraries name files by written pitch),
    per-note rather than per-file gain, per-spec tail caps, URL-escaped note names, and
    pruning of outputs the manifest no longer references.
  - **Bug fixed:** the vibraphone shipped an octave too low (VCSL's C3-is-middle-C naming).
  - **Bug fixed:** `test_playback_voices.py` had been failing since the license pass deleted
    `frontend/public/samples/bass/`; it now models sample-dir aliases and carries an explicit,
    self-checking list of the voices that synthesize on purpose.
  - Tests: frontend 29→71, backend 133(+1 red)→135 green. Sample tree 3.4 MB → 20 MB.

**Phase 1 complete. Phase 2 complete** apart from desktop runtime testing of the
custom-instruments MVP (below) — limiter, per-style FX, loudness normalization, the
velocity-layer engine, the license compliance pass, and the sample re-sourcing pass have
all landed. **The one open Phase 2 task** is the manual desktop pass on custom instruments
(import / assign / play / delete), which automation can't perform.
