# Design: First-Class Instrument Identity

**Status (2026-07-23):** **✅ COMPLETE — Phases 1, 2, and 3 all shipped.** The
instrument registry is now the single source of truth for identity, generation
profiles, GM programs, and in-app playback voices; the parallel frontend maps and
the backend legacy program map have been deleted.

- ✅ **Phase 1 — identity everywhere.** Registry lives in `backend/app/core/instruments.py`
  (`INSTRUMENTS`, `instrumentation_for`, `gm_programs_for`, `track_display_name`,
  `clamp_range`). All 31+ built-in styles carry an `instrumentation` block. GM
  programs and MIDI track names derive from it; `/styles` serves `instruments`
  + `voices`. Guarded by `backend/tests/test_instruments.py` (derived programs ==
  legacy, no monophonic-on-polyphonic-role).
- ✅ **Phase 2 — profiles drive generation.** `generate_chords` consumes the
  profile's `range` (`clamp_range`), `polyphony` (`_cap_polyphony`), and `strum`;
  `generate_bass` and `generate_melody` consume their profiles (range clamps +
  `_enforce_playing_profile` for breath/legato).
- ✅ **Phase 3 — playback unification (DONE, 2026-07-23).** All in-app playback
  voice selection now flows through the registry. Both frontend
  `STYLE_TO_INSTRUMENT` maps (`melodic.ts`, `bass.ts`) are **deleted**;
  `getBassSampler(voice)` and per-part `getMelodicSamplerById(voiceFor(...))`
  take the registry voice served by `/styles`. The backend `_STYLE_PROGRAMS`
  legacy map is **deleted** — `part_midi_meta` derives GM programs from the
  registry, with `_DEFAULT_PROGRAMS` as the sole custom-style fallback. Two new
  instruments (`slap_bass` GM 36, `fretless_bass` GM 35) were added, and bass
  `playback_voice` values are now fine-grained (one per sample set). The
  divergences were reconciled by ear via `docs/instrument-phase3-worklist.md`
  (kept as the decision record). Cross-language drift is guarded by
  `backend/tests/test_playback_voices.py` (every registry `playback_voice` must
  resolve to a real sample dir or synth family).

  **Audition note:** because picks favored the registry for some styles, in-app
  bass timbre changed for cloud_rap, dancehall, dark_ambient, dark_trap, drill,
  trap_soul, and the melodic bed moved to per-part voices for the ~11 mapped
  styles (e.g. jazz chords→Rhodes + melody→Alto Sax instead of one Vibraphone).
  Exported MIDI bass programs also shifted for ambient, boom_bap, cumbia,
  doom_metal, funk, hip_hop, lofi, metal, reggaeton, rock to match.

**Motivation:** parts are currently labeled by *role* (chords, melody, pads). Real
arrangements are built from *instruments* (Rhodes, upright bass, alto sax), and an
instrument's identity should shape what gets generated for it — a guitar comps
differently from a piano, a sax line breathes, an 808 slides. This doc makes
instrument identity a first-class concept that naming, generation, MIDI output,
and in-app playback all read from one source.

---

## 1. Current state (what already exists, scattered)

The system already makes real instrument decisions in **three disconnected places**:

| Mechanism | Location | What it decides | Visible to user? |
|---|---|---|---|
| `_STYLE_PROGRAMS` / `_DEFAULT_PROGRAMS` | `backend/app/services/mixdown.py` | GM program number per part per style (jazz bass = 32 Acoustic Bass, jazz melody = 65 Alto Sax…). Well-curated, ~20 styles covered. | Only as the patch a DAW picks; tracks are still *named* `chords`/`melody` |
| `STYLE_TO_INSTRUMENT` + FX chains | `frontend/src/soundfonts/melodic.ts` | Which sampled instrument the in-app preview uses for melodic parts (Rhodes, vibraphone, nylon guitar, clavinet, accordion, organ, strings) | Audible but unlabeled; **independent of the backend map — the two can disagree** |
| Style "playing knobs" | style JSONs (`comp_style`, `strum_speed`, `staccato_factor`, `chord_register`, `melody.range`, `bass.bass_style`, drum `character`) | How parts are *played* — strums, articulation, register, walking vs 808 bass | Indirectly (it shapes the notes) |

Problems with the status quo:

1. **Invisible**: a dragged-in MIDI file shows tracks named `chords`, `melody` —
   the arrangement reads as abstract data, not music.
2. **Two sources of truth**: backend GM programs and frontend playback voices are
   maintained separately and drift (e.g. trap_soul plays a Rhodes sampler in-app
   while its MIDI may declare a different program).
3. **Generation is instrument-blind**: the chords generator writes the same
   voicings whether the target is a 6-string guitar, a piano, or a pad. The
   melody generator writes the same lines for a monophonic sax as for a
   polysynth. Where instrument-appropriate behavior exists (bossa strums), it's a
   hand-tuned style knob that merely *coincides* with the instrument choice.

---

## 2. Goals / non-goals

**Goals**
- One place per style that says "the chords part IS a Rhodes" and everything
  downstream (track names, UI labels, GM programs, playback voice, playing
  behavior) derives from it.
- Generators receive an *instrument profile* and produce idiomatic material:
  correct range, polyphony, articulation, and phrasing for that instrument.
- Zero behavior change for styles that haven't been migrated (fallback = today's
  behavior), so rollout can be incremental and survey-verified per style.

**Non-goals**
- Audio synthesis realism (sample libraries, round-robins) — out of scope; the
  playback voices stay what they are, they just get *selected* consistently.
- User-facing instrument *swapping* in the UI (choose "guitar instead of piano").
  The schema should permit it later, but it is not part of this design's rollout.

---

## 3. Schema

### 3.1 Instrument registry (new file: `backend/app/instruments.json` or `.py`)

A single registry of named instruments. Each entry carries identity + playing profile:

```jsonc
{
  "rhodes_ep": {
    "display_name": "Rhodes EP",
    "gm_program": 4,
    "playback_voice": "electric_piano_1",   // frontend sampler/synth id
    "range": [28, 96],
    "polyphony": 8,
    "sustain": "decay",          // decay | sustain | ring
    "strum": 0.0,                // seconds between voiced notes (0 = block)
    "monophonic_legato": false
  },
  "upright_bass": {
    "display_name": "Upright Bass",
    "gm_program": 32,
    "playback_voice": "bass_sampler",
    "range": [28, 55],
    "polyphony": 1,
    "sustain": "decay"
  },
  "alto_sax": {
    "display_name": "Alto Sax",
    "gm_program": 65,
    "playback_voice": "melody_lead",
    "range": [49, 81],
    "polyphony": 1,
    "sustain": "sustain",
    "breath": true,              // insert phrase gaps; no overlapping notes
    "monophonic_legato": true
  },
  "nylon_guitar": {
    "display_name": "Nylon Guitar",
    "gm_program": 24,
    "playback_voice": "acoustic_guitar_nylon",
    "range": [40, 83],
    "polyphony": 6,
    "sustain": "decay",
    "strum": 0.018
  }
  // … 808_sub, supersaw_lead, warm_pad, string_ensemble, vibraphone, clavinet,
  //   accordion, drawbar_organ, marimba, flute, brass_section, piano …
}
```

### 3.2 Per-style instrumentation (added to each style JSON)

```jsonc
"instrumentation": {
  "chords":         "rhodes_ep",
  "bass":           "upright_bass",
  "melody":         "alto_sax",
  "arpeggio":       "vibraphone",
  "pads":           "warm_pad",
  "counter_melody": "string_ensemble"
}
```

Parts stay as the *roles* (the API contract, channel mapping, and regeneration
flows all key on them) — the instrumentation block binds each role to an
instrument. A style without the block behaves exactly as today.

**Migration is mostly mechanical**: initial instrumentation blocks can be
derived from the existing `_STYLE_PROGRAMS` entries + `STYLE_TO_INSTRUMENT`,
which is where the curation already happened. Conflicts between the two maps
(the drift problem) get resolved once, by ear, during migration.

---

## 4. Layer 1 — identity everywhere (small, safe)

Consumers of the instrumentation block, no generator changes:

- **MIDI track names** (`backend/app/services/midi_writer.py`, `track.name = part_name`
  sites): become `"Rhodes EP"` / `"Alto Sax"` (fall back to the part name).
  Keep the role in the track too (`instrument_name` meta or `"Alto Sax (melody)"`)
  so round-trip tooling that greps by part still works — **note:** the survey
  tool (`scripts/survey_songs.py`) and several tests parse tracks *by name*;
  they must switch to channel-based lookup (`_PART_CHANNELS` is stable) in the
  same change.
- **GM programs** (`mixdown.py`): read from instrumentation; `_STYLE_PROGRAMS`
  becomes the fallback for unmigrated styles, then is deleted at the end.
- **UI labels** (`frontend/src/components/PartCard.vue`, SongResult stems, ExportPanel):
  show `Rhodes EP` with the role as the small caption. The `/styles` API response
  gains the instrumentation block so the frontend needs no second copy.
- **Stem filenames**: optional, default off — `rhodes_ep.mid` reads better in a DAW
  session folder, but changing filenames breaks the regeneration API's
  part-name contract, so keep `chords.mid` and rely on track names inside.

## 5. Layer 2 — playing profiles drive generation (the "better feel")

Generators take the profile and *derive* what today are hand-tuned style knobs.
Existing style knobs win when present (they're per-style taste); the profile
fills in when absent. Touchpoints, by field:

| Profile field | Consumer | Behavior derived |
|---|---|---|
| `range` | `generate_chords` (`chord_register`), `generate_melody` (`melody.range`), pads register, bass clamps | Registers come from the physical instrument instead of per-style guesses. Melody-ceiling logic unchanged — it just caps *within* the instrument range. |
| `polyphony` | `generate_chords` voicing (`_voice_lead` candidates), pads | Guitar ≤6 voices with guitar-shaped (stacked-4ths/drop) voicings; piano up to 8–10; clav 2–3 stabs. Monophonic instruments can never get chord roles at all — validated at style load. |
| `strum` | `generate_chords` (`strum_speed`) | Strum timing from the instrument (guitar 15–25 ms, piano ~8 ms, pad 0). |
| `sustain` | `generate_chords` durations, pads, arpeggio release | `decay` instruments get natural note-length caps (a Rhodes chord doesn't hold 4 bars at full level — re-hit instead); `sustain`/`ring` hold. |
| `breath` | `generate_melody` | Enforce ≥ a 16th of silence between phrases, no overlapping notes, cap phrase length (a sax player runs out of air) — this alone should make sax/flute leads read as *played*. |
| `monophonic_legato` | `generate_melody`, bass | Overlap-trim + slur-friendly durations; 808 keeps its slides. |

Verification: extend `scripts/survey_songs.py` with two new instrument-aware
metrics — **range violations** (notes outside the declared instrument range)
and **polyphony violations** (simultaneous note count above the profile) — then
survey before/after per migrated style. These metrics are also exactly the
regression guard that keeps future generator work honest about instruments.

## 6. Layer 3 — playback unification

- `frontend/src/soundfonts/melodic.ts`: replace `STYLE_TO_INSTRUMENT` with a
  lookup of the style's instrumentation (served by `/styles`); `playback_voice`
  ids map to the existing sampler/synth builders. The per-instrument FX chains
  and volumes already keyed by instrument id survive unchanged.
- `useMidiPlayer.offlineRender`: pick stem voices from instrumentation so the
  WAV export matches the labels too.
- Drums are already instrument-aware (`DrumCharacter` presets) — fold the
  character name into the instrumentation block for consistency
  (`"drums": "linn_kit"`), purely a naming unification.

---

## 7. Rollout plan

1. **Phase 0 (this doc)** — agree on schema + registry field set.
2. **Phase 1** — registry + instrumentation blocks for all 31 styles (derived
   from the two existing maps), Layer 1 consumers, survey tool switched to
   channel-based track lookup. Behavior-identical apart from names/programs;
   full test suite + one survey sweep to prove no regression.
3. **Phase 2** — Layer 2 profile plumbing behind per-field fallbacks; migrate
   instrument families one at a time (guitars → winds → keys), surveying each
   with the new range/polyphony metrics before moving on.
4. **Phase 3** — Layer 3 frontend unification; delete `STYLE_TO_INSTRUMENT`
   and `_STYLE_PROGRAMS`.

## 8. Open questions

- **Where does taste live?** When a style knob (`strum_speed`) and a profile
  field disagree, the style wins — but should migrated styles *delete* their
  knobs to avoid two places to tune? Proposal: yes, delete on migration; the
  style JSON keeps only deliberate deviations.
- **Custom styles** (`backend/custom_styles/`): user-authored styles get the
  fallback path forever unless they add an instrumentation block; the style
  editor UI could offer a dropdown of registry instruments later.
- **Instrument swapping in the UI** — the schema supports a per-request
  `instrumentation` override cleanly (it's just a dict), but regeneration
  metadata (`song_meta.json`) would need to persist it. Defer.
- **Blended styles** (`blend_style_id`): whose instrumentation wins? Proposal:
  primary style's, always — blending affects patterns, not the band.
