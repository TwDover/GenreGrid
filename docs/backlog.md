# GenreGrid Backlog — post-roadmap nice-to-haves

_Created 2026-07-29. Phases 1–4 of [`roadmap.md`](roadmap.md) are complete and the three
companion roadmaps (`quality-roadmap-2`, `songcraft-roadmap`, `instrument-identity-design`)
are shipped. This is the parking lot for what's next: follow-ups from recently-landed work
plus the nice-to-haves surfaced in the July 2026 survey. Nothing here is firefighting._

**Status legend:** `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` won't do

---

## Tier 1 — highest leverage (start here)

- [ ] **Richer piano-roll editing.** Today you can only select → nudge → delete an existing
  note ([`PartCard.vue`](../frontend/src/components/PartCard.vue), [`PianoRoll.vue`](../frontend/src/components/PianoRoll.vue)).
  Add: draw/insert notes, drag to change length, edit velocity (drag height or a lane).
  Biggest lever on an otherwise very complete generator — it turns "regenerate until I like it"
  into "generate then shape it." Edits already persist via the stem-rewrite + History path,
  so the work is UI + the `EditPartRequest` note list.
- [ ] **Build around a chord progression or a drum groove** (not just a melody). The
  melody-upload path (Krumhansl key detect + Viterbi progression) is excellent; the same
  machinery can seed from an uploaded progression or groove. → `routes_song.py` melody-upload path.
- [ ] **MP3/OGG audio export.** Only WAV ships ([`ExportPanel.vue`](../frontend/src/components/ExportPanel.vue)).
  WAVs are large for sharing. `lameenc` is already a dep of the sample pipeline — add an encode
  pass on the offline-rendered buffer. Small, high user value.

## Tier 2 — feel / sound polish (ear-gated)

- [ ] **Tune `compound_swing` per style.** The 6/8/9/8/12/8 triplet lilt shipped with a single
  default (0.5, `humanize.apply_compound_swing`). With ears (via `/run-genregrid` playing a
  6/8 loop): ballads/grooves likely want more, orchestral/march 6/8 wants `compound_swing: 0`.
  Add the field to the styles that would use compound meter.
- [ ] **Odd-meter (7/8, 5/8) accent shaping.** Placement + backbeat are correct; a 2+2+3 accent
  contour (like the compound velocity contour) could sharpen the grouping. → `humanize.py`.
- [ ] **Meter-native feel velocity for compound.** `apply_feel`'s velocity contour is still a
  16-slot 4/4 curve indexed bar-relative; for compound it accents 4/4 quarter positions, not the
  dotted-quarter pulses. The `apply_compound_swing` contour now sits on top, but making
  `apply_feel` itself branch on `meter.is_compound` would remove the redundancy. → `humanize.py`.
- [ ] **True LUFS loudness normalization.** Current per-family master trims are hand-tuned
  ([`fxPresets.ts`](../frontend/src/soundfonts/fxPresets.ts)); a real offline-measured LUFS
  target per style would even out perceived loudness properly. Roadmap Phase 2 deferred this.
- [ ] **Finish the 4 synth-only voices** — clavinet, drawbar organ, accordion, nylon guitar —
  if a CC0/CC-BY multisample source turns up (none found in the Phase 2 pass; see
  [`LICENSE_AUDIT.md`](LICENSE_AUDIT.md) §6).

## Tier 3 — custom-instrument follow-ups (design doc has the detail)

See [`custom-instruments-design.md`](custom-instruments-design.md) §"Phased delivery" (4–5).
- [ ] **Multi-file kit slots** — the kit editor's slot picker assigns one file; the map already
  supports velocity layers / round-robins per piece.
- [ ] **Chromatic-instrument mapping preview** — a mini-keyboard to audition each zone (kit pieces
  already have per-slot audition).
- [ ] **SF2/SFZ import (T4)** — start with SFZ (text), then SF2 (binary, needs a parser).
- [ ] **Auto pitch-detection** on import (relax the note-named-file requirement).
- [ ] **Web/OPFS storage** — custom instruments are Electron-only today (blob: URLs from IPC);
  a browser build needs OPFS + object URLs.

## Tier 4 — workflow & polish

- [ ] **Undo depth beyond 5.** History caps at five states ([`README.md`](../README.md));
  a longer/unbounded per-song undo stack is cheap insurance for an editing tool.
- [ ] **Metronome / count-in** in the preview transport — small, and genuinely useful when
  auditioning odd/compound meters. → [`TransportBar.vue`](../frontend/src/components/TransportBar.vue).
- [ ] **Multitrack MIDI / DAW-project export** — a labeled multitrack `.mid` (or basic project
  file) to smooth the DAW handoff the app already leans into (drag-to-DAW exists).
- [ ] **Accessibility pass** — keyboard nav / ARIA on the transport, panels, and piano roll.
- [ ] **Changelog / "what's new" surface** — the feature set is deep now; discoverability is a
  growing cost.

## Tooling / infra

- [ ] **Grow the `/run-genregrid` skill** — more scenarios (generate + play a loop; WAV-export
  smoke). If the project's own e2e wants the driver, graduate it to `scripts/`/`e2e/` and update
  the skill's paths (see the skill's SKILL.md "Graduation" note).
- [ ] **Backend `pytest` in CI** if not already wired — the suite (235 tests) is fast (~17s).

---

## Recently completed (2026-07-29, this session — awaiting commit)

- Custom-instruments **desktop runtime pass** (13/13 checks) + fixed a kit-editing IPC bug
  ("An object could not be cloned"). → `useCustomInstruments.ts` (+ test).
- **`/run-genregrid`** Electron runtime-test skill (CDP driver + scenario + gotchas).
- **Non-4/4 feel bar-anchor fix** — humanize feel/pocket no longer drifts across bar lines.
- **Compound triplet swing** (6/8, 9/8, 12/8) — middle-eighth lilt + velocity contour, tunable.
