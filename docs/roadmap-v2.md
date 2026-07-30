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
  3. **Velocity** — drag note height, or a slim velocity lane under the roll.
  4. **Multi-select** — marquee + move/transpose a group; shift-click to extend.
  Persist through the existing path: `EditPartRequest` (note list, `max_length=5000`) → stem
  rewrite → `rebuild_combined_from_parts` → History snapshot (all already built).
- **Entry:** `PianoRoll.vue`, `PartCard.vue`; backend `edit-part` route + `EditedNote` schema
  already exist ([`routes_song.py`](../backend/app/api/routes_song.py), `schemas.py:220`).
- **Effort:** L (canvas interaction is the bulk; one component).
- **Risk:** interaction complexity — mitigate by shipping insert → resize → velocity → multi
  as four separate PRs. Pure note-mutation helpers should be unit-tested (mirrors the existing
  voiceRouting/offlineMix test style).
- **Done when:** you can build a bar from scratch in the roll, edits round-trip through
  save + History, and the mutation logic has tests.

### 5.2 MP3 / OGG audio export
- **Why:** only WAV ships ([`ExportPanel.vue`](../frontend/src/components/ExportPanel.vue));
  WAVs are large and awkward to share. This is the most-common "send someone the track" need.
- **Approach:** encode the offline-rendered buffer. Two options — **(a) renderer-side WASM**
  (`lamejs`/`@breezystack/lamejs`) keeps the offline path self-contained and offline; **(b)**
  POST PCM to the backend and use `lameenc` (already a pip dep of the sample pipeline).
  Recommend (a) for the browser build's sake. Add a format toggle to the Export row.
- **Entry:** `useOfflineRender.ts`, `ExportPanel.vue`, `wavEncoder.ts` (sibling encoder).
- **Effort:** S–M.   **Risk:** WASM encoder bundle size; keep it lazy-loaded.
- **Done when:** MP3/OGG buttons produce valid files that match the WAV mix bit-for-mix.

### 5.3 Multitrack MIDI / cleaner DAW handoff
- **Why:** drag-to-DAW and per-part stems exist, but importing N separate `.mid` files is
  fiddly. One labeled multitrack `.mid` (a track per part, correct GM programs, section
  markers, key/tempo) drops straight onto a DAW timeline.
- **Approach:** extend the combined-MIDI writer to optionally emit one track per part (it
  already writes a combined file + per-part files). Reuse the registry's GM programs +
  existing markers.
- **Entry:** `services/midi_writer.py` (`write_combined_midi`), `ExportPanel.vue`.
- **Effort:** S.
- **Done when:** a single exported `.mid` opens in a DAW as labeled, correctly-voiced tracks.

### 5.4 Seed from a progression or a groove (not just a melody)
- **Why:** the "build around my melody" path (Krumhansl key-detect + Viterbi progression) is a
  standout. The same machinery can start from an **uploaded chord progression** or a **drum
  groove** — two very common creative starting points.
- **Approach:** new SongForm inputs; backend accepts a progression (roman/chords) that bypasses
  pool selection (the `progression_override`/`custom_progression` seam already exists) or a
  groove `.mid` whose feel + kick/snare map is mined and drives the drums. Reuse `mining/`.
- **Entry:** `SongForm.vue`, `routes_song.py` melody-upload path, `mining/`.
- **Effort:** M.
- **Done when:** a song can be generated from an uploaded progression and from an uploaded
  groove, each round-tripping through replay.

### 5.5 Deeper undo + portable project files
- **Why:** History caps at 5 states ([`README.md`](../README.md)); and there's no portable
  *project* — songs live as loose stems reconciled from disk, so you can't hand a whole session
  to another machine or archive it cleanly.
- **Approach:** raise/soften the History cap (or make it per-song unbounded within a session);
  add **`.ggproj` export/import** — a zip of `song_meta.json` + stems — that restores a full
  session.
- **Entry:** History logic in `routes_song.py` + the frontend song store; a new project
  import/export surface.
- **Effort:** M.
- **Done when:** undo goes deep, and a project exports and re-imports faithfully.

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

---

## Phase 7 — Ship it well: reach & robustness

Concrete, mostly-known-scope work that widens who can use the app and keeps quality gated.

### 7.1 Frontend tests in CI  ✅ already in place (verified 2026-07-29)
CI already runs the frontend suite — the Linux job's **"Frontend tests"** step
(`cd frontend && npm test` → `vitest run`) gates every push alongside `vue-tsc` and `eslint`
([`.github/workflows/build.yml`](../.github/workflows/build.yml)). No gap here; an earlier
note that vitest wasn't wired was wrong (the step uses `npm test`, not `npm run test`). Left
in the roadmap as a verified checkpoint.

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

### 7.6 (new) Live playback-tempo control — "dial in the groove"
- **Why:** BPM is only settable *before* generation (SongForm / GenerateForm), and changing it
  regenerates the whole thing. A user auditioning a loop or shaping a part in the piano-roll
  editor often just wants to *nudge the tempo and feel it* — speed a lofi beat up, drag a 7/8
  groove slower — without a re-roll. There's now a transport in both the app
  ([`TransportBar.vue`](../frontend/src/components/TransportBar.vue)) and the roll editor
  ([`PianoRollEditor.vue`](../frontend/src/components/PianoRollEditor.vue)), so this fits right in.
- **Approach:** a **non-destructive** playback-tempo control (a small BPM scrubber / ± next to the
  transport, and one in the editor toolbar) that just sets `Tone.getTransport().bpm` — playback
  only, no regeneration. Show it relative to the generated BPM (e.g. "105 → 118") with a reset.
  Keep it distinct from the form's BPM (which *does* regenerate). Optional follow-up: an "apply
  tempo" that bakes the chosen tempo into the export/stems (WAV render already renders at the
  transport tempo; MIDI export would rewrite the tempo meta) — but the core win is the live feel.
- **Entry:** `TransportBar.vue`, `PianoRollEditor.vue` (its `▶` transport already drives
  `Tone.getTransport()`), `useMidiPlayer` (expose a `setPlaybackBpm`). **Effort:** S.
  **Risk:** keep the seeded-determinism invariant — a live tempo change must not alter generated
  note data; it's a transport speed only, and export stays byte-identical unless "apply" is used.

---

## Phase 8 — Bigger bets (spike, then decide)

Higher-risk, higher-ceiling. Each starts with a **spike** (a timeboxed prototype behind a flag)
to prove feasibility + demand before committing. Ordered by feasibility × payoff.

### 8.1 Live MIDI input (Web MIDI API)  — most natural fit
- **Why:** GenreGrid asks you to *upload* a melody; a musician wants to *play* one. Live MIDI
  input lets you capture a hook on a controller, seed the "build around my melody" path from a
  performance, and audition voices/custom instruments by playing them.
- **Approach:** `navigator.requestMIDIAccess()` in the renderer (Electron + Chromium support it;
  no native deps). Two surfaces: **(a) audition** — route note-on/off straight into the current
  voice/`LayeredSampler` for instant play (uses the audio engine as-is); **(b) capture** — record
  a short performance to a note list, quantize to the meter grid, and hand it to the existing
  melody-seed pipeline (which already does key-detect + progression derivation).
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

## Suggested sequence

1. **7.2** (code signing) — the current pick. macOS first (Gatekeeper *blocks*; unblocks
   auto-update too), Windows second (SmartScreen only *warns*). Gated on procuring the certs;
   until then it's a prepared spec, not a merge. _(7.1 — vitest in CI — is already done.)_
2. **Phase 5.1 → 5.2** (piano-roll editing, then MP3/OGG) — the biggest user-visible leap:
   shape output, then share it. 5.1 ships in four incremental PRs.
3. **5.3 + 5.4** (multitrack export, seed-from-progression/groove) — round out the workflow.
4. **Phase 6** opportunistically, ear-gated, interleaved with the above (6.1 is cheap and
   finishes this session's thread).
5. **Phase 8** — now planned in detail below; spike the one with the strongest signal after
   the workflow wins land.

## Measurement

Extend `scripts/survey_songs.py` and the frontend test suite as features land; keep the two
invariants that have carried the project: **seeded determinism** and **byte-identical gating**
on untouched paths. For anything touching *feel* or *mix*, the acceptance test is a real listen
via `/run-genregrid`, not a metric alone.
