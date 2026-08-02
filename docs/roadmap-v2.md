# GenreGrid Roadmap v2 — From complete to indispensable

_Created 2026-07-29. The original [`roadmap.md`](roadmap.md) (Phases 1–4) and the three
companion roadmaps are shipped: the app generates, arranges, scores, and sounds excellent,
in any meter, with custom instruments and a deep style system. This roadmap is the next
chapter — turning a great **generator** into a tool people reach for to **finish and ship**
music. It supersedes the `backlog.md` parking lot._

**How to read an item:** each carries **Why** (the user gap), **Approach**, **Entry points**,
**Effort** (S ≤ 1 day · M ≈ 2–4 days · L ≈ 1–2 weeks), **Risk**, and **Done when**.

**Principles carried over from every prior roadmap:** every new device is seeded and
deterministic; changes are gated so untouched paths stay byte-identical (the 4/4 invariant is
the template); shipped audio is CC0/CC-BY only; and the final judge of *feel* is ears in a DAW
— drive the app for that via the `/run-genregrid` skill.

---

## Phase 5 — Creator workflow: shape it and get it out

The generator is world-class; the thinnest part of the loop is what happens *after* a good
generation. Today that's "re-roll until you like it, then export a WAV." This phase makes
output **editable** and **portable** — the highest-leverage work on the whole app.

### 5.1 Full piano-roll editing  ★ flagship
- **Why:** the roll only supports select → arrow-nudge → delete on *existing* notes
  ([`PianoRoll.vue`](../frontend/src/components/PianoRoll.vue) `editable` mode). You can't add
  a note, change its length, or edit velocity — so you can regenerate but not *compose*.
- **Approach (incremental, in this order so each ships value):**
  1. ✅ **Insert** (shipped 2026-07-29) — mousedown on empty grid starts a drag-to-create; note
     snaps to the 0.25-beat grid (time) and nearest semitone (pitch), drag sizes length, a plain
     click makes a one-grid note; live preview while dragging; percussion parts are guarded
     (pitch → drum piece, so insert-by-pitch is disabled there). Pure math in
     [`utils/pianoRollEdit.ts`](../frontend/src/utils/pianoRollEdit.ts) (7 unit tests, round-trip
     against the draw transform); interaction covered by `PianoRoll.test.ts` (4 component tests
     driving real mouse events). Persists through the existing `notes-changed`→`saveEdits`→
     `editPart` path — no backend change.
  2. ✅ **Resize** (shipped 2026-07-29) — grab a note's right edge (a 6px zone, capped at
     half the note so short notes stay selectable) and drag to change duration; the end snaps
     to grid, start stays put, min one grid; an `ew-resize` hover cursor signals the grab. Pure
     `nearRightEdge`/`resizedDuration` in `utils/pianoRollEdit.ts` (+3 unit tests); interaction
     in `PianoRoll.test.ts` (+3 component tests: edge-drag lengthens 1.0→2.625, body-press
     selects, cursor only over the edge). Live-driven via `scenarios/resize-note.mjs`
     (note visibly grew ~0.26→0.58 of the roll). Same `notes-changed`→`saveEdits` path.
  3. ✅ **Velocity** (shipped) — a slim velocity lane under the grid; drag a note's bar to set
     its velocity, or drag a whole multi-selection at once. Pure `velocityFromLaneY`.
  4. ✅ **Multi-select** (shipped) — a Draw/Select tool toggle: marquee a group, Shift-click to
     extend, drag to move, arrows to transpose, ⌫ to delete. Pure `rectsOverlap`/`snapDelta`.
  Beyond the original four, a dedicated **zoomable editor** shipped
  ([`PianoRollEditor.vue`](../frontend/src/components/PianoRollEditor.vue), opened from a stem's
  **✎**): a piano-keyboard gutter with note names, a bar/beat ruler, a snap grid (1/4–1/32),
  zoom (buttons + ⌘/Ctrl-scroll) + scroll, **playback of the live-edited buffer** on the part's
  real instrument with a moving playhead, **click-to-audition** keys/notes, and a
  **loop region with draggable start/end flags** (drag the ruler to set it, grab a flag to move
  one edge). Persists through the existing path: `EditPartRequest` (note list, `max_length=5000`)
  → stem rewrite → `rebuild_combined_from_parts` → History snapshot.
- **Entry:** `PianoRoll.vue`, `PartCard.vue`; backend `edit-part` route + `EditedNote` schema
  already exist ([`routes_song.py`](../backend/app/api/routes_song.py), `schemas.py:220`).
- **Effort:** L (canvas interaction is the bulk; one component).
- **Risk:** interaction complexity — mitigate by shipping insert → resize → velocity → multi
  as four separate PRs. Pure note-mutation helpers should be unit-tested (mirrors the existing
  voiceRouting/offlineMix test style).
- **Done when:** you can build a bar from scratch in the roll, edits round-trip through
  save + History, and the mutation logic has tests.

### 5.2 MP3 / OGG audio export  ✅ shipped 2026-07-29
- **Why:** only WAV shipped; WAVs are large and awkward to share. This is the most-common
  "send someone the track" need.
- **Shipped:** a **WAV / MP3 / OGG** segmented toggle ([`AudioFormatToggle.vue`](../frontend/src/components/AudioFormatToggle.vue),
  backed by the app-wide [`useExportFormat`](../frontend/src/composables/useExportFormat.ts)
  singleton) sits on every audio-export surface — the loop workspace's Export row
  ([`ExportPanel.vue`](../frontend/src/components/ExportPanel.vue) Mix + Stems), the song
  result ([`SongResult.vue`](../frontend/src/components/SongResult.vue)), and per-part stems
  ([`PartCard.vue`](../frontend/src/components/PartCard.vue), which inherit the choice). The
  offline-rendered buffer is encoded by [`encodeAudio`](../frontend/src/utils/audioEncoder.ts):
  WAV stays the synchronous dependency-free `wavEncoder`; MP3/OGG go through `wasm-media-encoders`,
  whose convenience encoders **inline the LAME / Vorbis WASM as a base64 data URI** — so encoding
  is fully self-contained (no CDN/network), satisfying both the offline Electron shell and the
  strict-CSP browser build. The ~0.6 MB WASM is **dynamically imported**, so it code-splits into
  its own lazy chunk and only loads when a compressed export is first requested.
- **Approach chosen:** option (a) renderer-side WASM (kept the offline path self-contained),
  but via `wasm-media-encoders` rather than `lamejs` — one MIT dep covers **both** MP3 (LAME)
  and OGG (Vorbis), where lamejs is MP3-only.
- **Entry:** `useOfflineRender.ts` (threads a `format` arg → `encodeAudio`), `audioEncoder.ts`,
  `AudioFormatToggle.vue`, `useExportFormat.ts`.
- **Tests:** `audioEncoder.test.ts` (real WASM encode → valid MP3 frame-sync + OGG "OggS"
  magic, mono + stereo); `ExportPanel.test.ts` "5.2" block (toggle threads format into
  `offlineRender` + filename ext). Real-shell proof:
  `scenarios/export-mp3-ogg.mjs` generated a loop and exported valid `audio/mpeg` (383 KB,
  `FF FB…`) and `audio/ogg` (254 KB, `OggS`) in packaged Electron.
- **Done when:** ✅ MP3/OGG exports produce valid files from the same rendered mix as WAV.

### 5.3 Multitrack MIDI / cleaner DAW handoff  ✅ shipped 2026-07-29
- **Why:** drag-to-DAW and per-part stems exist, but importing N separate `.mid` files is
  fiddly. One labeled multitrack `.mid` (a track per part, correct GM programs, section
  markers, key/tempo) drops straight onto a DAW timeline.
- **Shipped:** the combined MIDI is written as a **type-1 multitrack** — a track per part with
  the registry's GM `program_change`, display track names (e.g. "Alto Sax (melody)"), plus the
  shared tempo/key/section-marker track ([`write_combined_midi`](../backend/app/services/midi_writer.py)).
  A **"Multitrack (.mid)"** export button downloads that single labeled file
  ([`ExportPanel.vue`](../frontend/src/components/ExportPanel.vue) `handleMultitrackDownload`).
- **Done when:** ✅ a single exported `.mid` opens in a DAW as labeled, correctly-voiced tracks.

### 5.4 Seed from a progression or a groove (not just a melody)  ✅ shipped 2026-07-29
- **Why:** the "build around my melody" path (Krumhansl key-detect + Viterbi progression) is a
  standout. The same machinery can start from an **uploaded chord progression** or a **drum
  groove** — two very common creative starting points.
- **Shipped — progression:** a **"Seed from a progression"** text input on `SongForm.vue`
  accepts roman numerals ("i VI III VII") *or* absolute chords ("Am F C G");
  [`progression_import.py`](../backend/app/services/progression_import.py) normalizes it to a
  roman list that plugs into the existing `progression_override` seam, bypassing the style's
  pool (tests: `test_progression_import.py`, `test_progression_mode.py`).
- **Shipped — groove:** a **"Seed from a groove"** drum-`.mid` upload
  (`buildSongFromGroove` → `/build-song-from-groove`) mines the feel + kick/snare map and
  overlays derived drum fields onto the style via the generator's `_overlay_groove` step
  (tests: `test_grooves.py`, `test_groove_pocket.py`, `SongForm.test.ts` "5.4" block).
- **Done when:** ✅ a song generates from an uploaded progression and from an uploaded groove,
  each round-tripping through replay.

### 5.5 Deeper undo + portable project files  ✅ shipped 2026-07-30
- **Why:** History capped at 5 states ([`README.md`](../README.md)); and there was no portable
  *project* — songs lived as loose stems reconciled from disk, so you couldn't hand a whole
  session to another machine or archive it cleanly.
- **Shipped — deeper undo:** `_MAX_SONG_VERSIONS` raised 5 → **50**
  ([`routes_song.py`](../backend/app/api/routes_song.py) `_snapshot_song`), so undo goes deep
  within a session; every re-roll/add/edit still snapshots first and a restore stays restorable.
- **Shipped — `.ggproj` portable projects:** a `.ggproj` is a zip capturing a whole session
  (every part stem + `song_meta.json` + `song_structure.json` + any `sections/`, plus a
  `project.json` manifest; version snapshots are intentionally omitted to keep it lean).
  `GET /export-project/{id}` streams it; `POST /import-project` restores it into a **fresh
  generation id** and returns the rehydrated `BuildSongResponse` (shared `_song_response_from_dir`
  helper, also now used by `/songs`). Import is guarded by a **whitelist + zip-slip check**
  (`_is_safe_project_member` rejects absolute paths, `..` traversal, and stray members) and
  entry-count / uncompressed-size caps. Frontend: a **↓ .ggproj** button on `SongResult.vue`
  and an **Import** control in the Songs rail (`HomePage.vue` `onImportProject` → opens the
  restored song). API in [`api.ts`](../frontend/src/services/api.ts) (`exportProjectUrl`,
  `importProject`).
- **Tests:** backend `test_song_features.py` — export→import round-trip (stems restore
  byte-for-byte, fresh id, same response), bad/incomplete-archive rejection, and the
  `_is_safe_project_member` traversal guard; frontend `projectApi.test.ts` (export URL + import
  multipart POST + error propagation).
- **Done when:** ✅ undo goes deep, and a project exports and re-imports faithfully.

---

## Phase 6 — Feel & sound: the "produced" ceiling

Correctness and arrangement are done; this phase chases the last 10% that separates "great
MIDI demo" from "record." Most items here are **ear-gated** — validate with `/run-genregrid`.

### 6.1 Meter feel: finish what this session started
- **Tune `compound_swing` per style** (6/8 ballads want more lilt; orchestral 6/8 marches want
  `0`) — add the field to the styles that use compound meter.
- **Odd-meter (7/8, 5/8) accent shaping** — a 2+2+3 velocity contour like the compound one.
- **Meter-native feel *velocity*** — `apply_feel`'s velocity curve is still a 16-slot 4/4 grid;
  branch it on `meter.is_compound` so it accents dotted-quarter pulses natively (removing the
  redundancy the compound-swing contour currently papers over).
- **Entry:** `services/humanize.py`, style JSON.  **Effort:** M.  **Risk:** ear-gated.

### 6.2 True LUFS loudness normalization
- **Why:** per-family master trims are hand-tuned ([`fxPresets.ts`](../frontend/src/soundfonts/fxPresets.ts));
  perceived loudness still varies by style. Roadmap Phase 2 explicitly deferred a real target.
- **Approach:** offline-measure integrated LUFS per style (a script under `scripts/`), store a
  per-style trim so every style hits a common target (e.g. −14 LUFS).
- **Effort:** M.  **Done when:** measured LUFS across styles sits within ±1 of target.

### 6.3 Custom-instrument follow-ups
From [`custom-instruments-design.md`](custom-instruments-design.md) §"Phased delivery" 4–5:
SF2/SFZ import (T4), **web/OPFS storage** (unblocks custom instruments in the browser build),
multi-file kit slots, chromatic-instrument mapping preview (mini keyboard), auto pitch-detection
on import. **Effort:** S each except SF2 (M–L). Sequence: OPFS → multi-file slots → chromatic
preview → SFZ → SF2 → pitch-detect.

### 6.4 Finish the 4 synth-only voices
Clavinet, drawbar organ, accordion, nylon guitar — if a CC0/CC-BY multisample source turns up
(none found in the Phase 2 pass; [`LICENSE_AUDIT.md`](LICENSE_AUDIT.md) §6). Opportunistic.

### 6.5 (new) Mix polish: per-part tone + a master EQ
- **Why:** the mix has a limiter, per-style FX, sidechain, and loudness trims, but no user tone
  control. A couple of tasteful per-part options (bright/warm tilt, light saturation) and a
  simple 3-band master EQ would let users finish a mix without a DAW.
- **Effort:** M.  **Risk:** scope creep toward a full mixer — keep it to presets, not a console.

### 6.6 Synthesizer / sound-design patch designer  ✅ shipped (2026-07-30)
**Done, and then some.** `soundfonts/synthPatch.ts` defines the `SynthPatch` shape (engine-aware:
`engine: 'subtractive'`), a pure `patchToNodeSpec`, and a context-aware `buildSynthFromPatch` that
renders identically in **live playback and offline export**. The seven built-ins are preset patches
(`synthVoices.ts` factories are thin wrappers, gated byte-identical by `synthPatch.test.ts`).
`components/SynthDesigner.vue` is the designer — oscillator, filter, **amp / filter / pitch**
envelopes, one LFO (filter or amp/tremolo), and a full FX chain (drive, bitcrusher, chorus,
vibrato, delay, reverb) — with a keyboard audition (dry, octave-shiftable), a saved-patch library,
and per-part assignment. `composables/useSynthPatches.ts` persists the library + assignments in
localStorage (browser build included); `voiceRouting.ts` resolves a `synth-patch` source above the
style defaults; `useMidiPlayer.ts` and `useOfflineRender.ts` build assigned patches from the same
factory. Delivered beyond the original plan:

- **Pitch envelope** (mono voices) — the per-note 808/kick attack drop.
- **FX on mono voices** — so a bass patch can be driven/saturated (filter stays internal).
- **Curated preset library** — 808 Sub / 808 Boom / 808 Trap, Reese, Acid, Supersaw Lead,
  Warm Pad, Pluck, all in a `BUILTIN_PATCHES` registry addressable by slug.
- **Style → patch kits** — a style suggests patches per part; one click assigns them (per-style,
  reversible). See `STYLE_KITS` in `useSynthPatches.ts`.
- **Custom-instrument samples now render in offline export** too (melodic, bass, drums) — closing
  the pre-existing gap where only synth voices exported. Patch > custom > built-in, mirroring live.

**Still reserved (not built):** the `engine` follow-ons — FM (`Tone.FMSynth`), wavetable, additive/
granular; and pitch envelope on **poly** voices (needs per-voice detune, unlike the mono path).

_Original plan follows._

### 6.6 (new) Synthesizer / sound-design patch designer  ★ new instrument source
- **Why:** today a part's timbre is either a **sampled** voice (identity sampler / custom
  multisample) or one of a handful of **hard-coded** Tone synth factories
  ([`synthVoices.ts`](../frontend/src/soundfonts/synthVoices.ts): melody lead, synth chords, arp
  pluck, pad, strings, synth bass, lo-fi). Those are chef's-choice patches — the user can pick
  *which* one via voice routing but can't **shape the sound itself**. There's no way to design a
  voice from first principles: choose the oscillator waves, dial pitch/detune, sculpt the ADSR,
  sweep a resonant filter, add an LFO, and print your own reverb/delay/drive. This turns
  GenreGrid from "pick a preset" into a real **subtractive synth** — a third instrument source
  alongside *sampled* and *custom*, and the natural home for the frequency-level sound design the
  hard-coded factories only hint at.
- **Approach (a data-driven patch, not more hard-coded factories):**
  1. Define a **`SynthPatch`** data shape (pure, serializable — the same discipline as
     `CustomInstrument`/`LayeredSamplerManifest`) with sections:
     - **Oscillators** (1–3): wave (`sine`/`triangle`/`sawtooth`/`square`/`pulse`, plus Tone's
       `fat*`), coarse semitone + fine-cent detune, unison `count`/`spread`, level, pulse-width;
       an optional sub-oscillator.
     - **Pitch:** global transpose, glide/`portamento`, optional pitch-envelope depth.
     - **Amp envelope:** ADSR (attack/decay/sustain/release) + level.
     - **Filter:** type (`lowpass`/`highpass`/`bandpass`), cutoff frequency, resonance `Q`,
       rolloff, and a **filter envelope** (its own ADSR + `baseFrequency`/`octaves`) — the piece
       that makes a saw *move*.
     - **Modulation:** one or two LFOs routable to pitch (vibrato), amp (tremolo), or filter
       cutoff — rate, depth, wave, tempo-sync option.
     - **FX chain:** reverb (size/decay/wet), delay (time/sync/feedback/wet), chorus, drive/
       distortion, bitcrusher — the nodes already used ad-hoc in `synthVoices.ts`, now
       parameterized and ordered.
     - **Output:** level + pan.
  2. A **`buildSynthFromPatch(patch, disposables, output)`** factory that assembles a
     `Tone.PolySynth`/`MonoSynth` + filter + LFOs + FX from the patch and registers every node in
     `disposables` — i.e. the existing `synthVoices.ts` pattern, but generated from data instead
     of a bespoke function per voice. The current seven factories become **preset patches**
     expressed in this format (proves the shape is expressive enough, and is the migration path).
  3. Wire it into routing as a new **`MelodicVoiceKind` / voice source** ('synth-patch') in
     [`voiceRouting.ts`](../frontend/src/composables/voiceRouting.ts), resolved *above* the
     style-default synth branch when a part has an assigned patch — mirroring how `hasCustom`/
     `hasSampler` win today. It must render identically in **live playback** (`useMidiPlayer`)
     **and offline export** ([`useOfflineRender.ts`](../frontend/src/composables/useOfflineRender.ts)),
     so both paths build from the same patch → same node graph.
  4. A **sound-design UI** — a `SynthDesigner.vue` panel (sibling to `InstrumentsPanel.vue`):
     oscillator/filter/env/LFO/FX controls, a keyboard to audition (reuse `audition.ts`), a
     preset picker seeded with the migrated factory patches, and a live meter. Save/load a patch;
     assign it to a part like a custom instrument (`InstrumentAssignments`).
- **Determinism & gating:** a patch is pure data rendered by a pure factory, so a saved patch
  reproduces byte-identically across live/export/replay — the seeded-determinism invariant holds
  by construction. Ship it **additively**: no part gets a patch by default, so every existing
  song renders byte-identically until a user opts in (the 4/4-invariant template). Migrating the
  seven built-ins to preset patches is the one change that touches current output — gate it with
  a golden-render diff (a patch-built voice must match its old factory sample-for-sample, or the
  presets stay cosmetic and the factories keep rendering until parity is proven).
- **Entry:** new `soundfonts/synthPatch.ts` (the shape + `buildSynthFromPatch`) and
  `components/SynthDesigner.vue`; `synthVoices.ts` (migrate factories → presets),
  `voiceRouting.ts` (new voice source), `useMidiPlayer.ts` + `useOfflineRender.ts` (build from a
  patch), `useCustomInstruments.ts` / `InstrumentAssignments` (assign a patch to a part),
  `audition.ts` (keyboard preview).
- **Effort:** L (the patch shape + factory + dual-path wiring is M; the designer UI with every
  control is the bulk — ship it incrementally: **osc + amp env** first, then **filter +
  filter-env**, then **LFO/mod**, then **FX** — each a usable increment, mirroring 5.1's
  insert→resize→velocity→multi cadence).
- **Risk:** UI surface area (many controls) and CPU with unison × polyphony (cap voices, warn on
  heavy patches). Relates to 6.3/6.4 (custom-instrument + synth-voice work) and, for sharing
  patches, to 8.5's `.ggstyle` file pattern — a `.ggsynth` export could reuse it.
- **Engine roadmap (design v1 to grow, don't box it in):** ship **subtractive** first — it
  covers the vast majority of "sound design from frequencies" and reuses Tone's `Synth`/`MonoSynth`
  primitives directly. But make the `SynthPatch` shape **engine-aware from day one**: a top-level
  `engine: 'subtractive'` discriminator (the same tagged-union discipline as `CustomInstrument.kind`)
  so later engines slot in as new variants instead of a schema break. Planned follow-ons, each a
  later increment behind that tag:
  - **FM** — Tone ships `Tone.FMSynth`/`Tone.PolySynth(FMSynth)`, so a `engine: 'fm'` patch
    (carrier/modulator ratio, modulation index, per-operator envelopes) is a near-term add, not a
    rewrite.
  - **Wavetable** — a custom oscillator via `Tone.setPeriodicWave` / a wavetable position
    parameter with morph; more work (wavetable storage + a morph UI) but the patch tag makes it
    additive.
  - **Additive / granular** — higher-ceiling, spike-gated; keep them as reserved `engine` values
    so the format anticipates them without v1 carrying the cost.
  Keeping v1 *subtractive-only in behavior* but *multi-engine in shape* is the point: users get a
  real synth now, and FM/wavetable land as new patch variants + designer tabs rather than a
  second synth system.
- **Done when:** a user can design a voice from oscillators/filter/env/LFO/FX, audition it on a
  keyboard, save it, assign it to a part, and have it render identically in playback and export;
  the seven built-in voices exist as editable preset patches; the patch→node factory is
  unit-tested and untouched songs stay byte-identical.

---

## Phase 7 — Ship it well: reach & robustness

Concrete, mostly-known-scope work that widens who can use the app and keeps quality gated.

### 7.1 Frontend tests in CI  ✅ already in place (verified 2026-07-29)
CI already runs the frontend suite — the Linux job's **"Frontend tests"** step
(`cd frontend && npm test` → `vitest run`) gates every push alongside `vue-tsc` and `eslint`
([`.github/workflows/build.yml`](../.github/workflows/build.yml)). No gap here; an earlier
note that vitest wasn't wired was wrong (the step uses `npm test`, not `npm run test`). Left
in the roadmap as a verified checkpoint.

### 7.1b Native "Save As" for exports  ✅ shipped (2026-07-30)
Exports (MIDI / WAV / ZIP) used a browser `<a download>`, so the desktop app dropped files into
Downloads via Chromium's download shelf — a browser feel, not a desktop one. Now a `save-file` IPC
handler (`electron/main.ts`) opens a native `showSaveDialog` (correct file-type filter, remembers
the last folder) and writes the bytes; `electron/preload.ts` exposes `electronAPI.saveFile`.
`useRenderQueue.ts` prefers the native save in Electron (anchor download stays the browser-build
fallback), and `useDownloadPrompt.ts` skips the in-app rename modal there so it's a single OS
dialog for name **and** location.

### 7.2 Code signing + notarization (macOS *and* Windows)  ★ real distribution gap
- **Why:** **both** the macOS and Windows jobs build **unsigned** (macOS sets
  `CSC_IDENTITY_AUTO_DISCOVERY: false`; Windows has no signing step). Result: macOS Gatekeeper
  blocks the DMG ("app is damaged / unidentified developer") and macOS auto-update can't work
  (updates must be signed); Windows SmartScreen warns on the `.exe`. Linux (AppImage/deb) is
  fine. This is the single biggest barrier to a non-technical user actually installing the app.
- **Approach — macOS (needs a paid Apple Developer account):**
  - Export a **Developer ID Application** cert as `.p12`, base64 it → secret `CSC_LINK`;
    add `CSC_KEY_PASSWORD`. For notarization add `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`,
    `APPLE_TEAM_ID` (or an App Store Connect API key).
  - electron-builder config (`package.json` `build.mac`): `hardenedRuntime: true`,
    `gatekeeperAssess: false`, an entitlements plist (allow JIT for Chromium), and
    `"notarize": { "teamId": "…" }` (electron-builder reads the `APPLE_*` env).
  - CI: drop `CSC_IDENTITY_AUTO_DISCOVERY: false`, pass the secrets as env, and **guard on the
    secret being present** so PRs/forks without secrets still build unsigned (don't break the
    open build). Sketch:
    ```yaml
    env:
      CSC_LINK: ${{ secrets.MAC_CSC_LINK }}
      CSC_KEY_PASSWORD: ${{ secrets.MAC_CSC_KEY_PASSWORD }}
      APPLE_ID: ${{ secrets.APPLE_ID }}
      APPLE_APP_SPECIFIC_PASSWORD: ${{ secrets.APPLE_APP_SPECIFIC_PASSWORD }}
      APPLE_TEAM_ID: ${{ secrets.APPLE_TEAM_ID }}
      CSC_IDENTITY_AUTO_DISCOVERY: ${{ secrets.MAC_CSC_LINK != '' }}
    ```
- **Approach — Windows:** an OV/EV code-signing cert (or a service like Azure Trusted Signing).
  Provide `CSC_LINK` + `CSC_KEY_PASSWORD` to the Windows job; SmartScreen reputation builds over
  time (EV is instant). Lower priority than macOS (SmartScreen only *warns*; Gatekeeper *blocks*).
- **Effort:** M (mostly cert procurement + secret plumbing + one CI pass each).
- **Risk:** needs paid certs; the config can't be validated in this repo without them — apply
  when the certs exist. Don't half-wire it into CI (an un-guarded signing config breaks the
  currently-working unsigned build).
- **Done when:** a released DMG installs on a clean Mac with no warning and auto-updates; the
  Windows installer runs without a SmartScreen block (or with reduced friction).

### 7.3 Accessibility pass
- Keyboard navigation + ARIA on the transport, drawers/panels, and the piano roll; focus
  management on modals; visible focus rings. **Effort:** M.

### 7.4 Metronome / count-in
- A transport metronome + optional count-in — small, and genuinely useful now that odd/compound
  meters exist (auditioning a 7/8 groove without a click is hard). **Entry:**
  [`TransportBar.vue`](../frontend/src/components/TransportBar.vue), `useMidiPlayer`. **Effort:** S–M.

### 7.5 First-run onboarding + "what's new"
- The empty state ("Your loops land here…") could guide a first generation in one click; and a
  lightweight changelog/what's-new surface helps discoverability now that the feature set is
  deep. **Effort:** S.

### 7.6 (new) Live playback-tempo control — "dial in the groove"  ✅ shipped (2026-07-30)
- **Why:** BPM is only settable *before* generation (SongForm / GenerateForm), and changing it
  regenerates the whole thing. A user auditioning a loop or shaping a part in the piano-roll
  editor often just wants to *nudge the tempo and feel it* — speed a lofi beat up, drag a 7/8
  groove slower — without a re-roll.
- **Shipped — non-destructive live tempo:** `useMidiPlayer` now tracks the track's `generatedBpm`
  (captured on load) and a live `playbackBpm`; `setPlaybackBpm`/`resetPlaybackBpm` set only
  `Tone.getTransport().bpm` (clamped 40–300). Because Tone schedules the parts in ticks at the
  native tempo, a `tempoRatio` (playbackBpm/generatedBpm, `1` when un-nudged) rescales the
  transport's real elapsed seconds back to native-time so the **seek bar, time readout, and editor
  playhead stay aligned with the notes**; `seek()` divides by the same ratio. The note data,
  duration, and every export path are untouched — the un-nudged path stays byte-identical by
  construction (ratio `1`).
- **UI:** a compact `− 149 BPM + ↺` control on the docked transport
  ([`TransportBar.vue`](../frontend/src/components/TransportBar.vue), shown once a track is loaded)
  and in the roll-editor toolbar ([`PianoRollEditor.vue`](../frontend/src/components/PianoRollEditor.vue),
  shown while playing) — ± buttons + scroll-wheel nudge, an accent "nudged" state, and a reset to
  the generated tempo. Both surfaces drive the same shared module state, so nudging is consistent.
- **Tests:** `PianoRollEditor.test.ts` (+1: the control appears only while playing and its ±
  drives `setPlaybackBpm`). Real-shell proof: `scenarios/live-tempo.mjs` generated a loop, played a
  part, and four "+" clicks moved the packaged-Electron transport 145 → 149 BPM while the card's
  generated metadata stayed 145.
- **Deferred (optional follow-up):** an "apply tempo" that bakes the chosen tempo into
  export/stems (WAV already renders at the transport tempo; MIDI export would rewrite the tempo
  meta) — the core live-feel win is done.
- **Done when:** ✅ the transport tempo can be nudged live in both the app and the editor without a
  re-roll, and generated note data / exports stay byte-identical.

---

## Phase 8 — Bigger bets (spike, then decide)

Higher-risk, higher-ceiling. Each starts with a **spike** (a timeboxed prototype behind a flag)
to prove feasibility + demand before committing. Ordered by feasibility × payoff.

### 8.1 Live MIDI input (Web MIDI API)  — most natural fit  · audition ✅ shipped 2026-07-30
- **Why:** GenreGrid asks you to *upload* a melody; a musician wants to *play* one. Live MIDI
  input lets you capture a hook on a controller, seed the "build around my melody" path from a
  performance, and audition voices/custom instruments by playing them.
- **Shipped — (a) audition:** a **MIDI In** toggle on the transport
  ([`TransportBar.vue`](../frontend/src/components/TransportBar.vue)) enables Web MIDI, lists
  input devices (an "All inputs" default + a per-device picker), and plays a connected controller
  through the **current voice** — pick which part the controller drives (melody/chords/bass/pads/
  arpeggio/counter-melody/drums). New [`useMidiInput.ts`](../frontend/src/composables/useMidiInput.ts)
  (pure `parseMidiMessage` + Web MIDI access, hot-plug via `onstatechange`, device filter) routes
  note-on/off into new `auditionOn`/`auditionOff` on `useMidiPlayer` (sustained via
  `triggerAttack`/`triggerRelease`, reusing the proven `_buildAudition` voice resolution;
  `LayeredSampler` gained a `triggerRelease` for true note-off, mono bass releases by time). With
  no style loaded the audition uses a **sustaining lead** (not the decaying piano) so held notes
  ring. **Low latency for live play:** audition triggers at `Tone.immediate()` (drops the ~100ms
  scheduler look-ahead) and the global `AudioContext` `latencyHint` was lowered `0.3 → 'interactive'`
  (~171ms → ~11ms output buffer) — a global tradeoff (the big buffer had guarded against
  heavy-graph underrun glitches; raise it back toward 0.1 if crackle reappears on weak hardware).
  Tests: `useMidiInput.test.ts` (7 — message parsing + routing to audition with scaled velocity,
  device filter, enable/disable). Real-shell verified in packaged Electron against a real APC mini mk2.
- **Still to do — (b) capture:** record a short performance to a note list, quantize to the meter
  grid, and hand it to the existing melody-seed pipeline (key-detect + progression derivation).
- **Entry:** a new `useMidiInput.ts` composable; `TransportBar.vue` (an input toggle + device
  picker); the melody-upload path in `routes_song.py` (capture feeds the same seam).
- **Effort:** M (audition is S; capture+quantize is the bulk).  **Risk:** device permission UX;
  quantization quality. **Spike:** wire audition-only first — it's a day and immediately useful.
- **Done when:** you can play a connected controller and hear the current voice, and capture a
  hook that seeds a song.

### 8.2 Audio-in → melody (hum/whistle → hook)
- **Why:** the lowest-friction way to get an idea *out of your head* is to sing it. Pitch-detect
  a hummed/whistled phrase into a melody that drives the whole song via the existing seed path.
- **Approach:** capture mic audio (`getUserMedia`) → monophonic pitch detection (autocorrelation
  / YIN, or a small WASM lib) → note segmentation → quantize to grid → the melody-seed pipeline.
  Shares the **auto pitch-detection** work from custom-instrument import (6.3) — build that first
  and reuse it.
- **Entry:** new `usePitchDetect.ts`; a record button on `SongForm.vue`; reuse the melody-upload
  backend seam.
- **Effort:** M–L.  **Risk:** pitch-detection robustness on real voices (noise, glissando,
  octave errors) is the whole game — the spike must be evaluated on messy input, not clean tones.
  **Spike:** offline-detect a handful of recorded hums and eyeball the note lists before any UI.
- **Done when:** a hummed 4-bar phrase becomes a usable, in-key hook.

### 8.3 Describe-your-track input ("vibe" → setup)
- **Why:** the Setup form is powerful but expert-facing (style, key, complexity, variation,
  feel, meter…). A newcomer wants to type "dark lofi, sad, slow" and get a good starting point.
- **Approach:** **rules-first, model-optional.** A tag/keyword → parameter map (mood/energy/era
  tags → style shortlist + key/mode + complexity/variation/feel/tempo), presented as a one-box
  input that *pre-fills the Setup form* (never a black box — the user sees and can tweak the
  result). This needs **no model** to ship value; an LLM mapping is a later enhancement, not a
  dependency. Leans on the existing style metadata + mined priors.
- **Entry:** a `vibeToSetup.ts` mapping (pure, unit-testable) + a small input above the Setup
  form; the style catalog for the shortlist.
- **Effort:** M (rules version).  **Risk:** mapping quality/coverage — keep it transparent
  (fills the form, doesn't hide it) so a mediocre guess is still a good starting point.
- **Done when:** common descriptions land on a sensible, editable Setup; the mapping is tested.

### 8.4 Post-generation arrangement editing
- **Why:** [`ArrangementBuilder.vue`](../frontend/src/components/ArrangementBuilder.vue) designs
  the section sequence *before* generation; after generating you can re-roll a section but not
  **reorder / resize / insert / delete** sections on a timeline. That's the natural next edit
  surface above the per-part piano roll (Phase 5.1).
- **Approach:** a section-timeline view on the song result: drag to reorder, resize bar counts,
  insert/duplicate/delete sections. The backend already regenerates single sections and rebuilds
  the combined song (`rebuild_combined_from_parts`), persists `song_meta.json`, and snapshots
  History — this is mostly a frontend timeline UI that drives those existing operations, plus a
  backend "reorder/insert section" that reuses the section-build path.
- **Entry:** `SongResult.vue`, `ArrangementBuilder.vue`, `routes_song.py` section ops.
- **Effort:** M.  **Risk:** keeping voice-leading/motif continuity coherent across reorders
  (seams re-thread `prev_voicing`/motif state) — reuse the song-builder's existing seam logic.
- **Done when:** a generated song's sections can be reordered/resized/inserted with the song
  rebuilt coherently, undoable via History.

### 8.5 Style sharing / community packs
- **Why:** users can already create custom styles (`create_custom_style`, validated); there's no
  way to **share** one. A file format + import/export turns the style system into an ecosystem.
- **Approach:** export a custom style (its validated JSON + any mined prior + attribution) as a
  `.ggstyle` file; import validates via the existing `CustomStyleRequest`. Optionally a small
  in-app browser for a curated pack. No server required — files first.
- **Entry:** `routes_styles.py` (`create_custom_style`, custom-style storage), `StyleEditor.vue`,
  `StyleBrowser.vue`.
- **Effort:** S–M.  **Risk:** validating/importing untrusted style JSON safely (bounds already
  enforced by the schema; keep `extra="allow"` fields inert). **Done when:** a style round-trips
  export → import on another machine and generates identically.

---

## Phase 9 — From generator to a MIDI DAW: capture · perform · arrange

_Added 2026-07-30, after the 8.1 audition spike made playback an instrument (low-latency Web MIDI
in). The next chapter turns GenreGrid into a place you **perform into** and **arrange freely** —
recording, looping, and editing your own MIDI alongside the generated parts. This is an
**extension of existing seams** (`/edit-part` note-list persist, section rebuild, the roll
editor's transport + loop region, History, `.ggproj`), **not a rewrite** — provided we lock the
9.0 model decisions up front. It stays entirely web-audio-native (Tone.js) — **plugin / VST
hosting is explicitly out of scope** (it would require a native audio engine, a different product;
decided against 2026-07-30)._

**Guardrail — determinism scope.** The seeded / byte-identical invariant governs **generation**.
Recorded/performed MIDI is **captured user data** (like an imported melody) — versioned in History
+ `.ggproj`, never regenerated. Keep that line bright so recording never fights the invariant.

### 9.0 Model decisions to make FIRST (cheap now, expensive later)
- **One note model** shared by generate + edit + record. Notes already flow through `EditedNote`
  → `/edit-part` → stem rewrite → `rebuild_combined_from_parts`. A recorded take is just a note
  list on that same path — **extend it, don't add a parallel record buffer.**
- **Record against musical time (`Tone.Transport` ticks), not wall-clock**, so live tempo (7.6)
  and loop-wrap are handled musically; quantize to the meter grid at save.
- **Renderer captures, backend persists** — same ownership split as edits today.
- **Record modes:** overdub (add) vs. replace (punch). Ship overdub first.

### 9.1 MIDI recording — record what you play  ✅ shipped 2026-08-01 (loop + song mode), builds on 8.1
- **Why:** you can *play* a controller (8.1 audition); the missing half is *capturing* it. This is
  the 8.1 "capture" surface, now the anchor of the DAW direction.
- **Approach:** a **record-arm** on a part + the transport captures live MIDI-in to a note list
  keyed by transport ticks; on stop, quantize to the snap grid and persist via `/edit-part` (loop)
  or the section-rebuild path (song), snapshotting History first. **Metronome + count-in (7.4) is a
  prerequisite — pull it forward.**
- ✅ **Loop-record / overdub in the roll editor (shipped 2026-07-30):** a **● Rec** button on
  [`PianoRollEditor.vue`](../frontend/src/components/PianoRollEditor.vue) arms recording — an
  optional count-in (7.4), then the loop region (or the whole part, bar-aligned) plays and each
  pass **overdubs** the notes you play in. `useMidiInput` gained an `onMidiNote` tap; captured
  note-on/off are timed off the transport (`seconds × tempoRatio`, matching the playhead), appear
  live, and on stop are **quantized to the snap grid** and persisted via the existing `commit()` →
  `notes-changed` → `/edit-part` path (History-snapshotted). Drum parts guarded off for v1. Tests:
  `PianoRollEditor.test.ts` recording block (overdub capture→quantize→commit; drum-part guard).
  Play-test follow-ups (2026-07-30): MIDI-in now **monitors the edited instrument's exact voice**
  (a `setAuditionTarget` override in `useMidiInput`, set while the editor is open); a **take
  auto-saves** on stop; an **undo/redo** stack (Ctrl/Cmd+Z · Shift+Z, toolbar ↶/↷) snapshots each
  committed change; and a real **persistence bug** was fixed — after `/edit-part` the piano-roll
  cache is now refreshed (`setMidiData`), since `prefetchMidi` no-ops on an already-cached URL and
  a reopened editor was showing pre-edit notes. (The 2026-07-30 auto-save-on-stop was later
  changed to **review-before-save**, see below.)
- ✅ **Song-mode recording + editor overhaul (shipped 2026-08-01):**
  - **Section-aware editor** — the editor takes the song's section layout (`sections` prop threaded
    `SongResult` → `PartCard` → `PianoRollEditor`): colored section dividers + name tabs in the grid,
    and a **"Loop a section"** selector that snaps the loop region to a section's bars. Arm a song
    part, loop the chorus, overdub into just that section; persisted via the existing `/edit-part`
    → `rebuild_combined_from_parts` + `_snapshot_song` (History) path — no new backend endpoint.
  - **Overdub loop-replay** — captured notes now sound on *every* loop pass (a looping `Tone.Part`
    re-triggers the prepared voice via new `player.scheduleAudition`), so a take builds up audibly.
    Fixes the old "overdubbed notes bake in only on the next replay" v1 limitation.
  - **Review-before-save** — stopping a take commits it as an **unsaved** (dirty) edit and enables
    *Save edits*; the user saves it or Undo (Ctrl/Cmd+Z) discards it. No more auto-save clobbering
    the stem with a bad take.
  - **Drums fully editable** — recording, click-to-audition, and Draw/Select all enabled for drum
    parts (previously guarded off); named per-piece lanes (GM drum-name map) + a **kit label** on
    the card; drum inputs outside the GM range (35–81) are ignored at the input boundary.
  - **Live-MIDI takes control** — opening a stem's editor auto-engages MIDI routed to the edited
    part; MIDI config moved out of the transport into a `MidiSettings` block in Setup; per-part
    **mute/solo moved onto each instrument row** (DAW-style).
  - **Backend fix** — `edit_part` referenced `style` before assignment for drums
    (`UnboundLocalError` → 500, surfaced as a CORS-stripped "Failed to fetch"); fixed + regression
    test (`test_edit_part_drums_rewrites_stem`).
  - **Still future:** replace/punch mode; honoring drum note *length* in playback (crash/ride are
    byte-identical-safe, closed-hat/kick would change existing songs — deferred).
- **Effort:** M (audition + transport + edit-part all exist; the new work is capture→ticks→quantize
  and the record-arm UX). **Risk:** timing accuracy + overdub/loop semantics — keep the note model
  unified (9.0) and quantize on save.

### 9.2 Free arrangement / clip timeline
- ✅ **First slice shipped 2026-08-01** (PR #140, `feat/song-timeline-rearrange`): the post-gen
  section timeline on [`SongResult.vue`](../frontend/src/components/SongResult.vue) gained
  **drag-to-reorder**, **insert** (a `+ section` picker), **duplicate** (⧉), and **delete** (✕),
  backed by a new `POST /rearrange-song-sections` ([`routes_song.py`](../backend/app/api/routes_song.py))
  that rebuilds the whole song from a new section template — reusing each surviving section's
  original seed via `source_index` (`RearrangeSectionDef`, [`schemas.py`](../backend/app/models/schemas.py))
  for content stability, with fresh quality-searched seeds for new/duplicated sections. Ripple
  effects (a moved verse reshaping a later chorus, first-of-type re-anchoring the motif) fall out
  naturally since the whole song replays. Blocked (400) while any part is locked. Snapshotted via
  the existing `_snapshot_song` History path — undoable like any other structural edit. Tests:
  `test_song_features.py` "9.2" block (reorder/insert/delete/duplicate/resize/lock-block/undo,
  8 tests) + `SongResult.test.ts`; real-shell proof `scenarios/rearrange-timeline.mjs` +
  `scenarios/insert-picker.mjs`.
- ✅ **Resize-UI gap closed 2026-08-01.** A drag handle on each section block's right edge
  (`.sr-tl-resize-handle`, mirroring the piano-roll's own note-resize interaction in 5.1) live-
  previews the bar count as you drag (a local `resizePreviewBars` flex override, no request in
  flight) and commits one `rearrangeSongSections` call on release with the final bar count,
  reusing the section's `source_index` for content stability like every other structural edit. A
  resize-ending click is swallowed so it doesn't also seek playback. Tests: `SongResult.test.ts`
  (+3: handle drag → correct bars + source_index, swallowed post-resize click, blocked while
  locked); real-shell proof `scenarios/resize-section.mjs` — dragging Intro's handle +4 bars
  worth of pixels resized it 4→8 bars exactly (`total_bars` 57→61), with drag-reorder still
  working immediately after.
- **Remaining scope beyond the first slice:** this is still section-block granularity (bars +
  section identity), not a true **track × time clip canvas** — no per-part clips, no placing
  *recorded* MIDI (9.1) as an independent movable/loopable region distinct from its section, no
  split. Whether that fuller clip model is worth building beyond what the section timeline already
  covers is an open call — the section timeline may cover most of the real workflow need.
  **Effort (full clip model):** L.

### 9.3 Automation lanes
- Draw volume / pan / send / **synth-patch params** over time. Scoping this (2026-08-01) found
  the four params aren't equally ready: **send** has no functional playback path at all (CC91 is
  written into stems but never read back — decorative, DAW-export-only) and **synth-patch
  params** are fully static once built (no live-modulation hook) — both real new architecture,
  not just a UI. **Volume** and **pan** were chosen for v1 since both have (or can cheaply get) a
  real per-part audio-graph hook.
- ✅ **Slice 1 shipped 2026-08-01 — uniform per-part output insert (prerequisite plumbing, not yet
  automation itself).** Before this, pan only existed for the 5 melodic parts (chords/melody/
  arp/pads/counter_melody) via a per-channel `Tone.Panner`; bass, drums, piano/sampler, and
  custom-instrument voices had **no** panner at all in live playback (offline export panned
  custom instruments but live didn't — a real live/export inconsistency, fixed as a side effect).
  Every part now gets one persistent `Gain` → `Panner` insert
  (new [`soundfonts/partInsert.ts`](../frontend/src/soundfonts/partInsert.ts), live-side;
  a local per-render equivalent in
  [`useOfflineRender.ts`](../frontend/src/composables/useOfflineRender.ts)) sitting between that
  part's voice(s) and its shared family bus — whichever voice the part happens to use (synth,
  sampled, the piano fallback, or a custom instrument) connects through the same insert, so a
  future automation curve applies uniformly regardless of underlying voice. Getting there also
  required de-sharing two caches that used to serve two different parts from ONE instance
  (`getPianoSampler` in [`loader.ts`](../frontend/src/soundfonts/loader.ts) and
  `getMelodicSamplerById` in [`melodic.ts`](../frontend/src/soundfonts/melodic.ts) are now keyed
  per part, not just per voice id) — otherwise two parts sharing a fallback voice couldn't carry
  independent automation. **Gated byte-identical**: a literal WAV-byte diff turned out to be the
  wrong tool (even identical code with a pinned seed produces tiny sample-level jitter run-to-run
  — humanize/Web-Audio floating-point summation order, already an accepted "inaudible" tolerance
  per `sumPartBuffers`'s own comment in that file); verified instead via direct runtime
  introspection of the live graph — gain stays 1.0 and pan matches the backend's `_PART_PAN`
  table to 15+ decimal places for melodic parts, 0 for bass/drums, exactly reproducing prior
  behavior. Full frontend suite (308 tests), typecheck, and eslint all clean.
- ✅ **Volume + pan automation lanes SHIPPED 2026-08-02.** Backend: `AutomationPoint`/
  `PartAutomation` (`schemas.py`) extend `EditPartRequest`; `_apply_automation_cc`
  (`mixdown.py`) overlays a drawn curve onto a part's CC list from `edit_part` only — a
  drawn pan curve replaces the single default CC10 point with its own breakpoints, a drawn
  volume curve adds CC7 breakpoints, and drums (which otherwise skip the melodic CC pass
  entirely) can carry automation too since every part already has its own output insert
  (Slice 1). No automation drawn → `[]`/`None` write identically (`write_midi`'s `cc_events`
  check is falsy either way), so the byte-identical invariant holds by construction.
  **No new persistence store** — like notes, a curve's truth lives in the CC7/CC10 events
  actually written into the stem, parsed back out on load via a new `curveFromCC` helper
  (`voiceRouting.ts`); this deliberately differs from `useSynthPatches`/`useDrumKitPatches`
  (legitimately cross-song instrument libraries) since automation is per-song data, a sibling
  of notes. **Tempo-nudge safety for free:** breakpoints are stored in seconds at the
  generated tempo (matching `ParsedNote.time`), so live scheduling via
  `Tone.getTransport().schedule()` inherits 7.6's tempo-nudge behavior with no bars/beats math
  — a curve with one point degenerates cleanly to today's static set, so there's no separate
  static-vs-automated code path (`applyPartAutomation` in `useMidiPlayer.ts` replaced the old
  `trackPan`/one-shot `insert.panner.pan.value = pan` entirely). Offline export
  (`useOfflineRender.ts`) schedules the same curves directly on the render's AudioParams via
  precomputed `linearRampToValueAtTime` calls — deterministic and smoother than live's
  short-ramp-per-breakpoint approximation, an accepted asymmetry (live can't know a future
  tempo nudge; export is always one-shot). **UI:** a Velocity/Volume/Pan mode toggle on the
  existing bottom lane in `PianoRollEditor.vue` (not three stacked lanes) — click empty lane
  space to insert a breakpoint, drag an existing one to move it, dbl-click to remove it; new
  pure geometry helpers (`valueFromLaneY`, `nearestAutomationPoint`, `insertAutomationPoint`,
  etc.) in `pianoRollEdit.ts` sibling to `velocityFromLaneY`. Auto-lock falls out for free
  (`PartCard.vue`'s `saveEdits()` already emits `'edited'` after every successful save,
  automation included). Tests: backend `test_song_features.py` (no-automation byte-identical
  + curve-baking, including the drums case); frontend `pianoRollEdit.test.ts`,
  `voiceRouting.test.ts`, `PianoRollEditor.test.ts` (lane-toggle/drag/dbl-click-remove),
  `PartCard.test.ts` (seconds→beats round-trip through the edit-part payload). Real-shell
  proof: `scenarios/automation-lane.mjs` drew a volume point and a pan point in packaged
  Electron, saved, and confirmed via a raw byte scan of the refetched stem that CC7 and CC10
  actually landed at the drawn values (a pan curve's first breakpoint reflecting the part's
  pre-existing style pan is expected — a curve starts from wherever the part already was, not
  a blank slate).

### 9.4 Audio recording + audio clips
- Mic/line-in via `getUserMedia`; record audio clips alongside MIDI (waveform UI, an audio-clip
  model, monitoring). A real step up in scope. **Effort:** L.

### 9.5 (optional) MIDI-OUT to external gear / a DAW
- Web MIDI **output** streams GenreGrid's parts + live performance to an external DAW or hardware
  in real time — clean interop, and it's how someone would route into their own instruments
  elsewhere. Small, self-contained, and fits the current stack (no plugin hosting involved).
  **Effort:** S. Opportunistic, not on the critical path.

_Plugin / VST hosting is intentionally **not** on this roadmap — it needs a native audio engine
(a second product) and doesn't fit the web-audio core. Removed 2026-07-30._

**Sequencing:** ✅ 7.4 (metronome/count-in) → ✅ 9.1 (recording: loop-record + song-mode, shipped
2026-08-01) → ✅ **9.2 first slice, including resize (reorder/insert/delete/duplicate/resize
section timeline, all shipped 2026-08-01)** → **9.3 in progress** (✅ Slice 1 — uniform per-part
output insert, shipped 2026-08-01; backend persistence + scheduling + lane UI still to build) →
9.4 (audio) by demand; 9.5 (MIDI-OUT) opportunistically.

---

## Suggested sequence

1. ✅ **Phase 5.1** (full piano-roll editing) — shipped: insert/resize/velocity/multi-select,
   the dedicated zoomable `PianoRollEditor.vue`, and its loop flags + transport.
2. ✅ **5.3 + 5.4** (multitrack export, seed-from-progression/groove) — shipped; workflow rounded out.
3. ✅ **5.2** (MP3/OGG export) — shipped: app-wide WAV/MP3/OGG toggle, lazy-loaded self-contained
   WASM encoder covering both compressed formats.
4. ✅ **5.5** (deeper undo + `.ggproj` portable project files) — shipped: History cap 5 → 50,
   and `.ggproj` export/import round-tripping a full session. **Closes out Phase 5.**
5. ✅ **7.6** (live playback-tempo control) — shipped: a non-destructive BPM nudge on the docked
   transport and in the roll editor; sets `Tone.getTransport().bpm` only, note data + exports stay
   byte-identical.
6. **7.2** (code signing) — real distribution gap but **gated on procuring paid certs**; until
   then it's a prepared spec, not a merge. _(7.1 — vitest in CI — is already done.)_
7. **Phase 6** opportunistically, ear-gated, interleaved with the above (6.1 is cheap and
   finishes this session's thread). **6.6** (the synth / sound-design patch designer) is the
   biggest new bet here — a whole new instrument source — so spike its patch shape + factory
   (migrate one built-in voice to a data patch and prove byte-identical parity) before committing
   to the full designer UI.
8. **Phase 8** — now planned in detail below; spike the one with the strongest signal after
   the workflow wins land. **8.1 audition SHIPPED** (low-latency Web MIDI in); its capture half is
   now the anchor of Phase 9.
9. **Phase 9 (DAW direction)** — ✅ **7.4 metronome → 9.1 MIDI recording** shipped (loop-record +
   song-mode section recording, 2026-08-01, on the unified `/edit-part` note model). ✅ **9.2 first
   slice, including resize** (section-timeline reorder/insert/delete/duplicate/resize, all shipped
   2026-08-01) — whether the fuller track×time clip model is worth building beyond the section
   timeline is still an open call. ✅ **9.3 automation lanes (volume + pan) shipped 2026-08-02**
   (Slice 1 — uniform per-part output insert — shipped 2026-08-01; CC7/CC10 baking + live/offline
   scheduling + the Velocity/Volume/Pan lane UI shipped 2026-08-02) → next up, 9.4 audio. The 9.0
   model decisions held (one note model, record against transport ticks, renderer-captures/backend-persists).
   Stays web-audio-native — **plugin/VST hosting is out of scope** (removed 2026-07-30); MIDI-OUT
   (9.5) is an optional interop nicety.

## Measurement

Extend `scripts/survey_songs.py` and the frontend test suite as features land; keep the two
invariants that have carried the project: **seeded determinism** and **byte-identical gating**
on untouched paths. For anything touching *feel* or *mix*, the acceptance test is a real listen
via `/run-genregrid`, not a metric alone.
