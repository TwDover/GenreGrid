# GenreGrid Roadmap

A living, prioritized roadmap from the July 2026 project survey. Check items off as
they land; add new findings under the right phase so nothing gets lost.

**Status legend:** `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` won't do / obsolete ·
`[→]` moved to another phase

_**2026-07-29 — Phases 1–4 complete.** Custom-instruments desktop pass done (+ a kit-editing
IPC bug fixed), non-4/4 drum feel validated + the feel-layer bar-drift fixed, and compound
triplet swing landed. What's next lives in **[`roadmap-v2.md`](roadmap-v2.md)** — the detailed
forward plan (creator workflow, sound ceiling, distribution, bigger bets). History below._

_Last updated: 2026-07-28 — Phases 1, 2 & 3 complete (Phase 2 bar the manual
custom-instruments desktop pass). Phase 3 delivered: "parallelize generation" retired as a
phantom (generation is ~0.5s; the real wait — the WAV export render — is now parallelised +
auto-pauses playback), deprecation warnings cleared, swallowed exceptions logged, the two
route god-files split into `services/`, `useMidiPlayer.ts` split 1228→610 across five focused
modules, and frontend tests grown 12→123. All smoke-tested in the app. Two optional cosmetic
moves deferred (`_do_build_song`, the `toggle` shell). **Now starting Phase 4 — features.**_

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
- [x] **User-uploaded custom instruments** (SF2/samples) + per-part instrument picker
  _(promoted from Phase 4; MVP built and desktop-runtime-verified 2026-07-29)_ — users add their own
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
  **Desktop runtime pass (2026-07-29) — DONE.** Driven end-to-end in the real Electron shell
  over CDP (import T1/T2/kit · IPC disk persistence · blob-URL materialize · **non-silent
  offline render of a melodic sample and a kit piece** — the Linux Web-Audio silence risk,
  clear · `LayeredSampler` builds from a blob manifest · kit-slot edit · global + per-style
  assign · panel/kit-editor render · delete-with-cleanup; 13/13 checks). **Found & fixed a
  real bug:** `updateKitSlot` passed a Vue reactive proxy through Electron's structured-clone
  IPC → *"An object could not be cloned,"* which silently broke all kit editing in the
  packaged app; fixed (`toPlain` before `save`) + regression test (`useCustomInstruments.test.ts`).
  **This was the last open Phase 2 task — Phase 2 is now fully complete.**
  **Follow-ups (optional):** multi-file kit slots, chromatic-instrument preview, SF2/SFZ
  import (T4), auto pitch-detection, web/OPFS storage.
  → `soundfonts/customInstruments.ts`, `soundfonts/customDrumKit.ts`, `soundfonts/audition.ts`, `composables/useCustomInstruments.ts`, `components/InstrumentsPanel.vue`, `electron/main.ts`

## Phase 3 — Performance & refactor ✅ COMPLETE (2026-07-28)

- [-] **Parallelize full-song section generation** — _obsolete: the premise was
  wrong._ Measured 2026-07-28: backend section generation is **0.5–0.8s** end-to-end
  (`_do_build_song`, every style, up to max complexity / 12-section templates), not the
  claimed "~1–2 min". Building a song never renders audio — it calls the backend (~0.5s)
  then plays back **live**, so the "1–2 min" was the song's own playback length (a 56-bar
  song at 120 BPM *is* ~112s of audio), not generation time. Parallelizing a sub-second
  step would *regress* latency (process-pool spawn + pickling > the serial work) and, per
  the dependency audit, isn't even embarrassingly parallel: the section loop threads real
  cross-section state (`prev_voicing` seam voice-leading, `verse_motif`/`rhythm_cell`
  motif glue, `type_theme` repeat reuse) and generation uses the process-global `random`
  module (17 `random.seed()` calls) so threads can't run it deterministically. The only
  genuinely CPU-heavy path is the **on-demand WAV export** (`offlineRender`, synth-only
  `OfflineAudioContext`) — tracked as a new item below.
  → `backend/app/api/routes_song.py`
- [x] **Speed up WAV export render** — _this is the real "1–2 min" wait, not generation._
  Measured 2026-07-28 (headless Chromium, real Web Audio, 112s song / 2,576 voices, graph
  matching `offlineRender`): **56.4s** with the full FX chain, **51.8s** with all FX removed.
  The actual Tone.js app render is ≥ this (per-voice JS wrappers, `standardized-audio-context`
  shims, `render(true)` yields). **The bottleneck is per-note voice synthesis (~92%), NOT the
  reverb (~8%)** — so caching the convolution IR is nearly worthless (an earlier guess, now
  disproven by measurement).
  **Shipped — parallel per-part render.** Empirically, concurrent `OfflineAudioContext`
  renders run on separate Chromium threads (probe: 4 contexts, 9.2s serial → 3.7s parallel,
  **2.48× on 8 cores**), so `offlineRender` now renders each part on its own context via
  `Promise.all` instead of one big context. The offline graph has no shared reverb — every
  voice runs its own delay/chorus/filter into a plain gain — so the per-part outputs SUM to
  exactly the old pre-limiter mix; the master soft-clip limiter is then applied once to the
  sum in a raw-WaveShaper pass that reproduces `makeMasterLimiter` bit-for-bit (curve =
  `softClipCurve` sampled Tone's way, `oversample='4x'`). Result is mathematically identical
  to the old single-pass render (bar float summation order), just parallelised. A single-part
  stem export keeps the limiter inline (nothing to parallelise). Validated: pure mix logic
  unit-tested (`offlineMix.test.ts`); full end-to-end run in real Chromium produces valid
  non-silent audio via the parallel path; `vue-tsc` + eslint + 96 vitest green.
  Smoke-tested working in the desktop app; playback auto-pauses on export as intended.
  _Optional telemetry:_ a precise desktop wall-time before/after was never captured (headless
  SwiftShader is ~10× slower than realtime, so it can't measure the real speedup) — the
  mechanism (2.48× concurrent-context probe) stands regardless.
  Bench harness: `frontend/scripts/bench_render.mjs` (drives cached Chromium over CDP; no display).
  → `frontend/src/composables/useMidiPlayer.ts` (`offlineRender`, `renderOfflineFast`,
  `sumPartBuffers`, `limitMix`)
- [x] **Extract song/arrangement logic out of route god-files into `services/`** —
  handlers should be thin. Done for the two biggest logic blobs, each verified by the 135
  backend tests + ruff: the **generation core** (`_run_attempt`, progression choice, style
  blend/groove overlay, voice-leading + quality helpers) → **`services/generation.py`**, and
  the **song arrangement engine** (`_generate_song_sections` — the 465-line section loop —
  plus its motif/voice-leading helpers, the combined-MIDI writer, and bridge-escape) →
  **`services/song_builder.py`**. Both route files (and the new services) now depend on
  `services/generation.py` instead of importing generation logic out of `routes_generate.py`.
  `routes_generate.py` **1299 → 636**, `routes_song.py` **1498 → 889**.
  _Deferred (optional):_ the song-build coordinator `_do_build_song` and a few
  regenerate/stem/version helpers still sit in `routes_song.py` between the endpoints; they
  could move into `song_builder.py` too, but the endpoints that call them are already thin.
- [x] **Split `useMidiPlayer.ts`** into focused composables — **1228 → 610 lines.** Five
  concerns pulled out: the offline WAV export → **`useOfflineRender.ts`** (`offlineRenderRaw`,
  `sumPartBuffers`, `partHasNotes`, `limitMix`, `renderOfflineFast`, `isRendering`); the
  shared style-classification Sets + `PLAYER_PARTS`/`PlayerPart`/`CHANNEL_PART` →
  **`playerConstants.ts`** (playback + render read one source, no import cycle); the 7 synth
  voice factories → **`soundfonts/synthVoices.ts`** (next to `synthDrums.ts`; they take the
  player's `disposables` array so cleanup still disposes their nodes); and the pure
  voice-routing decision (which instrument a part plays) + the CC10 pan map →
  **`voiceRouting.ts`** (`resolveMelodicVoiceKind` / `panFromCC10`), so the fragile branch
  logic is unit-testable — `getMelodicInstrument` now switches on the returned kind. The
  pause-on-export stays a thin wrapper in `useMidiPlayer` (it owns the playback refs);
  `useMidiPlayer` re-exports `PLAYER_PARTS`/`PlayerPart` so external importers are unaffected.
  Pure moves — verified by `vue-tsc` + eslint + production build + 123 vitest. The scheduler's
  per-note trigger callbacks (mute gating, the kick sidechain pump, trigger args) also came out
  → **`scheduler.ts`** (`drumTriggerCallback` / `voiceTriggerCallback`), injected into
  `toggle`'s `Tone.Part`s. **1228 → 610 lines.**
  Smoke-tested in the desktop app (playback + WAV export + per-part mute all good).
  _Deferred (optional):_ `toggle`'s shell (async sampler load → graph wiring → transport
  control) is now mostly I/O orchestration — its extractable logic is out and tested; moving
  the shell itself is cosmetic and high-risk without runtime audio, so left as-is.
- [x] **Log swallowed exceptions** — audited all 27 broad `except` blocks. 12 already
  logged or re-raised; 6 genuine silent faults now log — `record_export_keep`
  (`routes_library.py`, warning), malformed groove/genre priors (`priors.py`, warning),
  library keep-merge on a corrupt prior entry (`library.py`, debug), style-load for track
  names (`routes_song.py` ×2, warning), and the arpeggio chord-tone derivation
  (`routes_generate.py`, debug). The rest were left deliberately: `mido_key_signature`'s
  `except` is by-design control flow (exotic modes have no MIDI key sig, documented), and
  the generator inner-loop `except`s (bass/melody/quality/answer/corpus) are intentional
  musical graceful-degradation, not swallowed faults — logging each would be pure noise.
- [x] **Grow frontend test coverage** — 12 → **123 tests**. The two fragile areas the
  survey flagged now have real coverage. WAV-render path: `offlineMix.test.ts`
  (`sumPartBuffers` mixing + `partHasNotes` channel→part mapping), `wavEncoder.test.ts`
  (`encodeWav` RIFF header, stereo interleaving, int16 clamping, mono byte-rate). Live
  playback: `voiceRouting.test.ts` (the melodic voice-selection precedence table + CC10 pan)
  and `scheduler.test.ts` (the `Tone.Part` trigger callbacks — mute gating, the kick sidechain
  pump, and trigger arguments, all driven without a Tone context via injected collaborators).
  The scheduler logic became testable by extracting the callbacks (see the split above); the
  remaining untested surface is `toggle`'s async sampler-load / graph-wiring I/O, which is
  integration-shaped rather than unit-testable.
- [x] **Clear deprecation warnings** — **Starlette `TestClient`**: moved the test dep from
  `httpx` to `httpx2` (`requirements.txt`); TestClient prefers httpx2 and the
  `StarletteDeprecationWarning` is gone, 135 backend tests still green. **Electron
  `console-message`**: rewrote the handler for the Electron 36+ single-`details` signature
  (string `level` instead of the deprecated positional numeric level — which the old code
  also mapped wrong). → `frontend/electron/main.ts`

## Phase 4 — Features

- [x] **Expose the data-driven priors toggle in the UI** — a "Use my local MIDI corpus"
  checkbox is on both the loop (`GenerateForm`) and song (`SongForm`) forms, bound to
  `form.use_priors` and threaded through `handleGenerate` → `generate()` → the request body
  → the backend's `use_priors`. It was already wired; the earlier "no control yet" note was
  stale (priors are gitignored, so on a fresh clone no style reports `has_prior` and the
  toggle self-hid). Now the toggle **always renders**: enabled for styles that have a mined
  prior, and shown **disabled with a "mine a MIDI corpus for this style to enable" hint**
  otherwise, so the feature is discoverable before you've mined anything.
  → `frontend/src/components/GenerateForm.vue`, `SongForm.vue`
- [~] **Non-4/4 time signatures** (6/8, 3/4, 7/8) — **Milestone 1 (foundation) shipped.**
  A `Meter` model (`core/meter.py`) centralizes the math: `bar_beats` (bar length in
  quarter-beats — 4/4→4.0, 3/4→3.0, 6/8→3.0, 7/8→3.5), compound/odd detection, and pulse
  positions (unit-tested across 4/4, 3/4, 6/8, 7/8, 9/8, 12/8, 5/8). `time_signature` added
  to all request schemas; the MIDI writer emits the correct `time_signature` meta (compound
  clicks on the dotted quarter). The meter is threaded end-to-end through the generation core
  — all 7 generators (which were already internally parameterized by a local `beats_per_bar`),
  `_plan_sections`, and the section loop. **4/4 stays byte-identical (135 backend tests green)**
  and non-4/4 runs end-to-end with correctly-sized bars + meta.
  **Milestone 2 (mostly shipped 2026-07-29):** the meter is now threaded through the song
  services — `song_builder` passes `time_signature` to every section request and scales all
  bar→beat arithmetic (section offsets, tease/outro windows, the ending bar), and the
  arrangement helpers (`_song_tempo_map`, `_apply_section_ramp`, `apply_arrangement_dynamics`,
  `apply_melodic_pickups`, `_section_end_bars`, `_section_markers`) take a `meter` and place
  ramps/dropouts/pickups/tempo-map/markers at meter-scaled positions. The regen/replay/undo
  paths persist `time_signature` in `song_meta.json` and thread it back through. Generators no
  longer overflow a short/odd bar: the **walking bass** steps one note per felt pulse
  (`meter.pulse_positions`) off 4/4; the **drum grid** clips its 16-step mined patterns,
  double-kick, jazz ride and bar-2 anticipation kicks to the bar and shifts end-of-bar
  fills/rolls/ghosts to the real bar end (`fill_shift = bar_beats − 4`); the **riff** cells
  space and clip to `bar_beats`. A **frontend time-signature selector** (curated simple /
  compound / odd list) is on both the loop and song forms and round-trips through replay.
  81 placement tests cover 4/4·3/4·2/4·6/8·9/8·12/8·7/8·5/8 (onsets stay in-bar, walking-bass
  note-count = pulse-count, song length + `time_signature` meta), and **4/4 stays
  byte-identical** (216 backend tests green; explicit `Meter(4,4)` == default per generator).
  **Idiomatic feel — landed (`8eb0f2c`) and validated 2026-07-29.** The snare **backbeat now
  lands on the meter's felt pulses** (`pulse_positions`) — 6/8→1.5, 12/8→1.5 & 4.5, 7/8→1.0,
  5/8→1.0, 3/4→2 — and **compound meters (6/8, 9/8, 12/8) use an eighth-note (grouped-by-three)
  hat grid** instead of a clipped 16th grid (`compound_feel` in `generators/drums.py`).
  Validated by generating drum loops in every meter across boom_bap / house / afrobeats and
  measuring onsets + accents against `pulse_positions` (backbeats on-pulse everywhere,
  compound hats at ~0.5-beat spacing, **zero bar overflow**). **Bug found & fixed en route:**
  the shared **feel/swing micro-timing** (`humanize.apply_feel` / `apply_groove_pocket`) indexed
  every note by a fixed 4/4 16-slot grid (`start/0.25 % 16`), so in any non-16-sixteenth bar the
  groove's micro-timing *drifted across bar lines* rather than repeating per bar — the residual
  "swings like a clipped 4/4." Now anchored to the bar (`_bar_slot`, threaded `meter`); **4/4
  stays byte-identical** (224 backend tests green; new regression `test_groove_pocket.py`).
  **Compound triplet swing — landed 2026-07-29.** Compound meters (6/8, 9/8, 12/8) now get a
  dedicated lilt pass (`humanize.apply_compound_swing`): a middle-eighth **timing swing** (the
  "DUM-da-dum" roll — verified in HTTP output, 6/8 & 12/8 middle-eighth hats move 0.5→~0.58)
  plus a per-dotted-quarter **velocity contour** (head strong, middle ducked, pickup light).
  Purely positional so every part lilts together; tunable per style via a `compound_swing`
  field (0 = straight march, 1 = hard shuffle; default 0.5). **Gated** — 4/4/simple/odd are a
  no-op (235 backend tests green; `test_compound_swing.py` covers the lilt + the no-op). The
  generators still emit straight, on-grid eighths (`test_compound_hats_ride_eighth_grid` still
  passes); the swing is a separate feel-layer pass, keeping placement and feel cleanly split.
  _Optional next (ear-gated):_ tune `compound_swing` per style with ears (some 6/8 ballads want
  more lilt, orchestral 6/8 marches want 0), and consider odd-meter (7/8) accent shaping. →
  `backend/app/services/humanize.py`, `backend/app/services/generation.py`, `backend/app/core/meter.py`
- [→] **Custom soundfont / SF2 upload** — _promoted to Phase 2 (Sound polish)._
- [x] **Surface WAV/offline-audio export more prominently** — the OfflineAudioContext
  render + queue existed but the WAV/Stems buttons were lost in a single long action row
  (Copy·Replay·Save·Share·Download·ZIP·WAV·Stems) with a cryptic ⚡ and no signal audio
  export existed. Split out a labelled **Export** row that separates **Audio** (accent-styled
  `⏬ WAV` / `⏬ Stems (WAV)`) from **MIDI** (`All parts (ZIP)` / `Sections (ZIP)`), so audio
  export reads as a first-class action. → `frontend/src/components/ExportPanel.vue`
- [x] **Tempo automation & mid-song modulation** — _mid-song modulation was already
  fully shipped_ (`chorus_key_shift` on every chorus, `bridge_key_shift` to the subdominant,
  `final_chorus_lift` gear-change on the last chorus — all with SongForm controls). The gap
  was **tempo automation**: the song tempo map (chorus push + pre-chorus lean + ending
  ritardando) existed but was hardcoded and invisible. Now a **`tempo_automation` knob**
  (0–1) scales all three gestures via `m = intensity/0.5`: **0 = flat/steady**, **0.5 =
  the classic subtle default** (byte-identical to before), **1 = expressive** (double depth).
  Exposed as a **Tempo motion** control (Off / Subtle / Expressive) on the song form,
  threaded through build + melody-upload + every regen/replay path (persisted in
  `song_meta.json` so re-rolls stay sample-locked). → `core/arrangement.py` (`_song_tempo_map`)

---

## Done log

- **2026-07-28 — Phase 3 performance & refactor (first pass):**
  - **Retired "parallelize section generation"** — measured generation at **0.5–0.8s**
    (not the claimed 1–2 min), so parallelising it would only add process overhead. The real
    "1–2 min" is the on-demand **WAV export render** (~56s, headless-Chromium bench).
  - **Parallel per-part WAV export** — `offlineRender` now renders each part on its own
    `OfflineAudioContext` concurrently (Chromium runs them on separate threads — measured
    2.48× on 8 cores), sums them, and applies the master limiter once in a raw-WaveShaper
    pass that reproduces `makeMasterLimiter` bit-for-bit. Mathematically identical to the old
    single-pass mix. Pure mix logic unit-tested (`offlineMix.test.ts`); real-browser e2e
    produced valid audio. Desktop wall-time number still to confirm.
  - **Auto-pause playback on WAV export** — the render walks the timeline on the main thread
    and starved the live Transport scheduler (playback froze mid-export); `offlineRender` now
    pauses playback for the duration (MIDI export was never affected).
  - **Route god-files split into `services/`** — generation core → `services/generation.py`,
    song arrangement engine → `services/song_builder.py`. `routes_generate.py` 1299→636,
    `routes_song.py` 1498→889; killed the route→route generation import.
  - **Deprecation warnings cleared** — test dep `httpx`→`httpx2` (Starlette TestClient);
    Electron `console-message` rewritten for the 36+ single-`details` signature.
  - **Swallowed exceptions logged** — 6 genuine silent faults now log (`record_export_keep`,
    malformed priors, style-load for track names, …); by-design fallbacks left alone.
  - Tests: backend 135 green + ruff clean; frontend 92→96 green + `vue-tsc`/eslint clean.

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

**Phase 1 complete. Phase 2 complete** — limiter, per-style FX, loudness normalization, the
velocity-layer engine, the license compliance pass, the sample re-sourcing pass, and the
custom-instruments MVP have all landed. The custom-instruments **desktop runtime pass ran
2026-07-29** (driven over CDP in the real Electron shell; 13/13 checks, non-silent user-sample
audio verified) and **found + fixed a kit-editing IPC bug** — see the custom-instruments item
above. No open Phase 2 tasks remain.
