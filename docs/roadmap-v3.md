# GenreGrid Roadmap v3 — Composition intelligence (no corpus required)

_Created 2026-08-04. Source: a code evaluation of the generation core looking for
musicality improvements that need **no corpus mining / learned priors** — every item here is
pure music-theory + search logic. **This roadmap takes priority over the remaining
[roadmap-v2](roadmap-v2.md) items**; v2 stays the reference for its unshipped entries
(6.4's last synth voice, 6.6 patch designer, 7.x ship-polish, 8.3, 8.5, 9.2/9.3/9.5), which
resume after v3 or when one blocks a user need._

**The through-line:** the non-corpus machinery is already sophisticated (phrase-plan form
grammar, motif seeding, voice-led comping, ensemble pushes, quality-gated search). What's
missing is **coordination between layers** — the phrase plan and the harmony don't talk, the
melody wanders instead of aiming, the chorus generator rarely emits what the hook scorer
rewards, and the search re-rolls blindly instead of repairing what its own scorer flagged.
Phase 10 makes the judge honest, Phase 11 makes the layers agree, Phase 12 is polish.

**How to read an item:** each carries **Why**, **Approach**, **Entry points**, **Effort**
(S ≤ 1 day · M ≈ 2–4 days · L ≈ 1–2 weeks), **Risk**, and **Done when**.

**Principles carried over:** every new device is seeded and deterministic; changes are gated
so untouched paths stay byte-identical (the 4/4 invariant is the template — new musical
behaviors default off / opt-in per style, scorer *corrections* are the exception since they
fix wrong answers); each shipped item bumps at least the minor version; the final judge of
*feel* is ears in a DAW via `/run-genregrid`.

**Measurement baseline — ✅ shipped 2026-08-04.**
[`scripts/quality_baseline.py`](../scripts/quality_baseline.py) sweeps all styles × a fixed
seed set and stores per-dimension scores, attempt counts, and a per-case hash of the
generated notes as [`docs/quality-baseline-v3.json`](quality-baseline-v3.json). Every item
below re-runs the same sweep; "scores improve / attempts drop" claims are judged against
that file, and the byte-identical invariant is the hash check.

```bash
python scripts/quality_baseline.py                                   # rewrite the baseline
python scripts/quality_baseline.py --compare docs/quality-baseline-v3.json
python scripts/quality_baseline.py --compare docs/quality-baseline-v3.json \
       --require-identical                                           # exits 1 if any note moved
```

`--compare` re-runs using the *baseline file's own* config and seeds, so the two are always
comparable, and prints per-dimension deltas plus a count of cases whose notes changed. The
sweep is library-neutral (it never saves) and takes ~60 s. Three suites:
`arrangement` (all styles, 16 seeds, 16 bars — the primary), `loop_chorus` (the app's
default single-section path), `meters` (6 styles × 3/4, 6/8, 7/8, 5/4 — feeds 10.2).

**Current baseline (mean over the winning attempt of each case) — after 10.1:**

| suite | cases | total | all-green | attempts | harmonic | separation | rhythm | contour | density | mix | hook |
|---|---|---|---|---|---|---|---|---|---|---|---|
| arrangement | 560 | 0.899 | 75.2% | 1.94 | 0.953 | 0.912 | 0.924 | **0.803** | 0.838 | 0.940 | **0.790** |
| loop_chorus | 280 | 0.902 | 78.2% | 1.90 | 0.957 | 0.919 | 0.906 | **0.804** | 0.889 | 0.940 | **0.791** |
| meters | 192 | 0.815 | **0.0%** | **5.00** | 0.961 | 0.905 | **0.513** | 0.852 | 0.836 | 0.938 | 0.728 |

_First capture at `e44e7ed` (pre-10.1), for reference: arrangement 0.897 / 74.8% / 1.96
attempts / harmonic 0.949; loop_chorus 0.901 / 78.2% / 1.90 / 0.954; meters 0.812 / 0.0% /
5.00 / 0.950._

What the baseline already confirms, before any item ships:

- **10.2 is worse than the roadmap assumed.** Every non-4/4 case fails: `rhythm` collapses
  to 0.51 (vs 0.92 in 4/4), *nothing* goes green, and all 192 cases burn the full 5-attempt
  budget chasing noise. Non-4/4 generation currently costs 2.5× the search time of 4/4 for
  a strictly worse result.
- **`contour` (0.804) and `hook` (0.790) are the weakest 4/4 dimensions**, both below the
  0.82 green line on average — exactly what 11.2 and 11.3 target. `mix` sits at 0.940 in
  every suite and every style, so it discriminates nothing.
- **Four styles never go green in 4/4 and always burn all 5 attempts** — arrangement:
  `trap_soul` (rhythm 0.50), `doom_metal`, `hyperpop`, `rock`; loop: `trap_soul`,
  `cloud_rap`, `hyperpop`, `rock`. That's ~11% of the sweep paying 5× search cost for
  nothing, and it's the headline case for 11.4's targeted repair.
- Overall mean attempts is 1.96 (arrangement), so 11.4's "≥ 30% drop" means landing ≤ 1.37.

Caveat: the scorer blends library-learned rhythm patterns into its reference
(`build_scoring_style`), so a library that grows between two sweeps moves scores on its
own. The baseline records per-style library counts (441 entries at capture) and `--compare`
warns when they differ. `scripts/batch_generate.py` writes to that library — pass
`--no-save` when using it for measurement.

---

## Phase 10 — Make the judge honest (scorer truth)

The best-of-5 search can only be as good as its scorer, and the scorer currently gives
wrong answers in two situations. These are the cheapest wins on the whole roadmap: they
improve **every existing generation path** (loop, song builder, regen) with no new musical
machinery. Ship both before anything in Phase 11, because Phase 11's items are tuned
against scorer feedback.

### 10.1 Score against the chords that actually sound  ★ ✅ shipped 2026-08-04
- **Why:** melody/bass/arp are generated against `s_resolved` — the per-section
  progression **after** `resolve_progression` applies 7th/9th swaps, secondary dominants,
  and tritone subs — but `score_generation` receives the raw pre-substitution
  `progression` ([`generation.py:745-749`](../backend/app/services/generation.py)) and
  rebuilds its chord map from that. Any attempt that used a substitution is scored against
  chords that aren't sounding, so `harmonic` mis-scores exactly the adventurous attempts —
  the search systematically prefers the blandest harmony, and the chromatic-color and
  substitution features fight their own quality gate.
- **Approach:**
  1. In `_run_attempt`, collect `(section_offset_beats, section_bars, s_resolved)` for every
     section as it's generated (the data already exists in the loop).
  2. Add an optional `resolved_sections` parameter to `score_generation`; when present,
     `_build_chord_map` builds the map from the actual per-section resolved romans (each
     section's key shift applied — chorus-lift sections resolve in the shifted key) instead
     of tiling the raw progression.
  3. `_harmonic_coherence` and everything downstream needs no change — they consume the map.
  4. This is a scorer *correction*, not a gated behavior: scores are expected to shift.
     Re-baseline after shipping (the events themselves are byte-identical; only scores and
     therefore *future* attempt selection change).
- **Entry:** [`generation.py`](../backend/app/services/generation.py) `_run_attempt`,
  [`quality.py`](../backend/app/services/quality.py) `_build_chord_map` / `score_generation`.
- **Effort:** S.
- **Risk:** attempt selection changes everywhere (different winning seeds for the same
  request). Acceptable — that's the point — but land it in its own PR so any perceived
  regression bisects to it. Existing `test_musicality.py` thresholds may need retuning.
- **Done when:** a unit test proves a tritone-sub progression scores identically whether the
  melody was generated against it or against the raw progression's map is *removed* — i.e.
  the new test asserts the substituted chord map is what gets scored; batch sweep shows
  `harmonic` no longer anti-correlates with `chromatic_color`/substitution activity.
- **Shipped:** `_run_attempt` records `(offset, bars, key, bar_beats, chords_per_bar,
  romans)` per section and passes it to `score_generation` as `resolved_sections`;
  `_build_chord_map_from_sections` builds the map from that. Two mis-bins beyond the
  substitution gap turned out to be in the same code path and are fixed with it: the map
  used the *request's* global complexity to pick chords-per-bar while the generators use
  the per-section `harmony_complexity` (so every boosted chorus was scored on slots twice
  as long as the ones playing), and it ignored the section's key (chorus-lift sections were
  scored in the unlifted key). `_style_match` deliberately still reads the raw progression —
  its corpus bigrams are mined from template-level romans.
  Tests: `backend/tests/test_quality_chord_map.py` (10).
  **Measured** (vs. the pre-10.1 baseline): styles that actually use substitutions or
  chromatic color (7 of 35) gained **+0.019 harmonic** and **−0.116 attempts**, against
  **+0.0007 / ±0.000** for the 28 that don't — the anti-correlation the item predicted,
  confirmed and removed. Biggest movers `rnb +0.061`, `jazz +0.046`, `soul +0.032`.
  Overall arrangement attempts 1.96 → 1.94, all-green 74.8% → 75.2%. 142 of 1032 cases
  picked a different winning attempt, as expected for a scorer correction.

### 10.2 Meter-correct scoring (finish roadmap 6.1's reach)
- **Why:** [`quality.py`](../backend/app/services/quality.py) hard-codes
  `_BEATS_PER_BAR = 4`; in 3/4, 6/8, or 7/8 the 16-step rhythm vectors, the chord map, and
  the hook self-similarity bars are all computed on a wrong bar grid — every non-4/4
  generation is quality-gated by noise. **The chord map is already done:** 10.1's
  `_build_chord_map_from_sections` takes each section's real `bar_beats`, so the production
  path is meter-correct there (only the legacy `_build_chord_map` fallback still assumes 4).
  What remains is the rhythm vectors, the hook bars, and the three stragglers below — and
  the baseline says that remainder is the whole problem: non-4/4 `rhythm` sits at 0.513
  against 0.924 in 4/4, nothing goes green, and all 192 meter cases burn all 5 attempts. The same hard-coded 4 survives in three other spots
  the 6.1 meter work didn't reach: `_chord_tones_by_bar`
  ([`generation.py:80`](../backend/app/services/generation.py)) mis-bins the arp's chord
  tones, `_section_scales` ([`generation.py:687`](../backend/app/services/generation.py))
  mis-spans the melody clean-up passes' section windows, and the bebop-run / approach-run
  beat math ([`melody.py:638,661`](../backend/app/generators/melody.py)) finds "strong
  beats" on a 4/4 grid in any meter.
- **Approach:**
  1. Thread `meter: Meter` into `score_generation` and `extract_rhythm_patterns`; replace
     `_BEATS_PER_BAR` with `meter.bar_beats` and size step vectors as
     `round(meter.bar_beats * 4)` steps (12 for 6/8, 20 for 5/4…). Style reference patterns
     (`kick_pattern`, `chord_rhythm`) are 16-step 4/4 authored data — when the meter isn't
     4/4, compare only the dimensions that have meter-native references (snare beats from
     `snare_standard_beats` convert cleanly; skip the 16-step cosine rather than compare
     mismatched grids).
  2. Fix the three stragglers with the already-threaded `meter` param (all three functions
     are called from meter-aware scopes).
  3. Hook scorer bars (`_hook_score`, `extract_rhythm_patterns` callers) use the same grid.
- **Entry:** `quality.py` throughout; `generation.py` `_chord_tones_by_bar`,
  `_section_scales` block; `melody.py` bebop/approach-run blocks;
  [`core/meter.py`](../backend/app/core/meter.py) (exists, no changes expected).
- **Effort:** M (mechanical but touches every scorer dimension; tests are the bulk).
- **Risk:** 4/4 must stay byte-identical **and score-identical** (bar_beats = 4.0 makes
  every formula collapse to today's). Guard with a regression test comparing 4/4 scores
  before/after on fixed seeds.
- **Done when:** a 6/8 and a 7/8 generation score with correctly-binned rhythm vectors
  (unit tests with hand-placed events), 4/4 scores are bit-identical to the baseline, and
  the non-4/4 batch sweep's attempt counts drop (the search stops chasing noise).

---

## Phase 11 — Make the layers agree (composition intelligence)

### 11.1 Cadence-aware harmony — the phrase plan drives the chords  ★ highest audible win
- **Why:** [`phrase_plan.py`](../backend/app/theory/phrase_plan.py) decides each phrase is
  *open* (half cadence) or *closed*, and the melody lands on sd2/sd5 or the tonic
  accordingly ([`melody.py:404-441`](../backend/app/generators/melody.py)) — but the
  harmony underneath just keeps cycling the section's template loop. A melody landing
  "open" over whatever chord happens to fall there doesn't read as a half cadence. Aligning
  the phrase-final chord with the planned cadence is the classic, cheap, most audible
  "written by a human" upgrade available.
- **Approach:**
  1. **Hoist phrase planning out of `generate_melody` into `_run_attempt`.** Plan once per
     section (seeded with `_part_seed(seed, section_i, "phrase_plan")`) and pass the
     `list[PhrasePlan]` into `generate_melody` (new optional param; when omitted, melody
     plans internally exactly as today — that keeps non-participating callers byte-identical).
  2. **Cadence substitution on `s_resolved`:** for each 4-bar phrase, rewrite the final
     chord slot — open → dominant-function (V in major, V or VII in minor; keep the slot's
     existing extension suffix), closed → tonic (I/i). Only the *last* slot of the phrase
     changes; mid-phrase harmony is untouched.
  3. **Gate per style:** `cadence_alignment` (0–1 probability, default **0** = byte-identical).
     Roll once per section, seeded. Enable at 0.7–1.0 for song-form styles (pop, rock,
     cinematic…) after listening; leave vamp-centric styles (house, techno, lofi) at 0 —
     a loop that never cadences is *correct* for them.
  4. Chords, bass, pads, and arp all consume `s_resolved` already, so the band agrees for
     free. The scorer sees the rewritten romans via 10.1's `resolved_sections`.
- **Entry:** `generation.py` `_run_attempt` (plan + substitution), `phrase_plan.py`
  (no change to shapes), `melody.py` (accept `plans` param),
  [`styles/*.json`](../backend/app/styles/) (per-style opt-in).
- **Effort:** M.
- **Risk:** a forced V can collide with `push_windows` anticipation or the pre-chorus ramp
  (`song_builder.py` already swaps the whole progression there — skip cadence rewrite for
  pre-chorus sections). Melody's cadence targeting assumes the *key's* sd2/sd5, which are
  chord tones of V — so alignment improves it, not fights it.
- **Done when:** with `cadence_alignment: 1.0`, every open phrase ends on dominant harmony
  and every closed phrase on tonic (unit test on resolved romans); A/B listening across
  3 song-form styles says phrases "breathe"; all-styles sweep with the gate at 0 is
  byte-identical.

### 11.2 Skeleton-first melody — goal tones, then motion  ★ flagship
- **Why:** the note loop ([`melody.py:324-614`](../backend/app/generators/melody.py)) picks
  direction by weighted coin flips shaped by the plan's contour peak — it *tends* toward
  the peak but never commits to arriving anywhere. Lines lack intent: no guaranteed peak
  arrival, no guaranteed agreement at chord changes, and sustained notes blunder across
  chord boundaries (patched after the fact by `_resolve_avoid_notes`, which only catches
  m2/m9).
- **Approach (two-pass, keeping today's machinery as the second pass):**
  1. **Skeleton pass:** for each chord slot in the phrase, choose one *goal tone* — a chord
     tone of that slot's resolved roman, register interpolated along the phrase plan's
     contour (rising into `contour_peak`, falling after; the climax phrase's peak goal is
     the highest goal in the section). Cadence slots reuse the existing open/closed
     targeting. Seeded; ~1 goal per chord change.
  2. **Elaboration pass:** the existing random walk runs *between* consecutive goals — same
     stepwise/leap/syncopation/density logic, but the walk's direction weights come from
     "which way is the next goal" instead of the phrase-position heuristic, and the walk
     must land on (or within a step of) the goal by its beat. Durations clip at goal
     boundaries, which kills most cross-chord clashes at the source.
  3. All ornament layers (trills, bebop runs, grace notes, motif blocks, A→A' pairing)
     operate on the result unchanged.
  4. **Gate:** style field `melody_engine: "goal"` vs default `"walk"` (byte-identical).
     Migrate styles one by one, by ear.
- **Entry:** `melody.py` (new `_plan_goal_tones` + direction-weight rewiring; the diff is
  localized to the direction/duration logic), `phrase_plan.py` (goals read plan fields that
  already exist).
- **Effort:** L (the generator is the heart of the product; test/listen budget dominates).
- **Risk:** over-constraint can make lines sound like exercises — keep the walk's freedom
  *between* goals (goals are ~1 per bar, not per beat). Mitigate by shipping behind the
  gate and A/B-ing per style. Interaction with `seed_motif` replay: motif replay overrides
  the first goal segment (theme statement wins).
- **Done when:** with the goal engine on, the section's highest note lands inside the
  planned climax phrase ≥ 95% of seeds (unit test), `_resolve_avoid_notes` fires measurably
  less often (log counter over the sweep), contour/harmonic scores improve on the
  baseline, and blind listening prefers it on ≥ 2 of 3 migrated styles.

### 11.3 Bar-level hook construction for choruses
- **Why:** `_hook_score` rewards bar-to-bar rhythmic self-similarity, but the generator
  only produces repetition through 2-bar block transforms with a 27% chance of exact
  repeat — the search hunts for hooks the generator rarely emits. Worse, the global
  max-2-consecutive-same-pitch rule ([`melody.py:825-846`](../backend/app/generators/melody.py))
  actively fights hookiness: repeated notes are the backbone of most pop hooks.
- **Approach:**
  1. When `section_type` is chorus/post_chorus (and the style opts in via
     `hook_tiling: true`, default false), generate **bar 1 as the figure** with the
     existing note loop, then tile **AAAB**: bars 2–3 replay bar 1's rhythm + pitches
     (velocity re-humanized, the existing `_vary_repeat` treatment), bar 4 keeps the rhythm
     but rewrites the tail to the phrase's cadence target (open on chorus-internal
     phrases, closed at the end). 8-bar choruses tile AAAB AAAB' with the second B closing.
  2. Relax anti-repetition to allow 4 consecutive same pitches in chorus sections (the
     post-process already knows nothing of sections — thread `section_type` in, or run it
     only outside choruses).
  3. The chorus's `seed_motif` (verse theme) seeds bar 1's opening so the hook still
     develops the song's idea.
- **Entry:** `melody.py` (tiling branch + anti-repetition gate), `song_builder.py`
  (no change — theme cache and tease already consume whatever the chorus melody is).
- **Effort:** M.
- **Risk:** AAAB can sound mechanical in jazz/cinematic styles — that's what the per-style
  gate is for. The hook scorer will strongly prefer tiled attempts, so once a style opts
  in, effectively every chorus uses it; make sure bar 1 itself is good (it inherits the
  goal-tone engine from 11.2 when both are on).
- **Done when:** hook dimension scores for opted-in styles jump on the sweep (target:
  median ≥ 0.82), the intro tease and hook-echo ending audibly carry the same figure, and
  a pop-style A/B says the chorus is more singable.

### 11.4 Targeted repair — the search fixes what the scorer flagged
- **Why:** the quality search ([`song_builder.py:329-347`](../backend/app/services/song_builder.py),
  [`routes_generate.py` `_run_best_attempt`](../backend/app/api/routes_generate.py))
  regenerates the **entire attempt** up to 5 times hoping the dice land better, even when
  the scorer says exactly one dimension failed. The `regen_part` plumbing to re-roll a
  single part already exists.
- **Approach:**
  1. After attempt 1, inspect per-dimension scores. If exactly one dimension is below
     green, apply its *repair* instead of a full re-roll:
     - `mix` → deterministic velocity rescale of the offending part (no regeneration);
     - `separation` → re-roll chords (`regen_part="chords"`) with the same seed salted;
     - `rhythm` → re-roll drums;
     - `contour` / `hook` → re-roll melody;
     - `density` → re-roll the flagged part (flags name it).
  2. Re-score after repair; if still failing or ≥ 2 dimensions red, fall back to today's
     full re-roll loop. Cap total work at the existing `_MAX_QUALITY_ATTEMPTS` budget
     (a repair costs one attempt slot).
  3. `harmonic` has no cheap repair (harmony is shared) — full re-roll, as today.
  4. Fully deterministic: repair choice is a pure function of the score dict; salts derive
     from the attempt seed. Replay (`fixed_section_seeds`) must record enough to reproduce —
     store `(seed, repairs)` instead of bare seed, or make repairs a deterministic replay
     of the winning seed's score (preferred: re-running the attempt re-derives the same
     scores, hence the same repairs).
- **Entry:** a new `services/repair.py` (score → repair-plan function, unit-testable pure),
  `song_builder.py` search loop, `routes_generate.py` `_run_best_attempt`.
- **Effort:** M.
- **Risk:** the replay contract (byte-identical regen of untouched sections) is the subtle
  part — the "repairs re-derive deterministically" design keeps `section_seeds` shape
  unchanged. Verify with the existing regenerate-song-part tests.
- **Done when:** on the sweep, mean attempts-per-green-section drops ≥ 30% and final section
  quality is ≥ baseline; regenerate-part/section round-trips stay byte-identical.

### 11.5 A tension curve across the song
- **Why:** velocity/density arcs exist, but harmonic tension isn't modeled anywhere.
  `resolve_progression`'s substitutions fire with flat probability regardless of where a
  section sits in the arc — verse 1 is as likely to get a tritone sub as the bridge. The
  bridge should *be* the tension peak; the outro should relax.
- **Approach:**
  1. New `theory/tension.py`: per-section **target tension** from section type + position
     (intro 0.2 → verse 0.35 → pre-chorus 0.6 → chorus 0.5 → bridge 0.8 → final chorus
     0.65 → outro 0.2; scaled by the `dynamics` macro), and a **measured tension** for
     scoring: non-chord-tone melody ratio + substitution/extension density + mean register
     height, normalized.
  2. Thread the target into `_run_attempt` → `resolve_progression` (substitution
     probability scales with target) and `generate_melody` (chromatic/blue-note and
     leap probabilities scale mildly).
  3. Optional scorer dimension (weight ~0.08): |measured − target|, only in song-builder
     mode where section types exist. With 11.4, its repair is "re-roll harmony".
  4. Gate: `tension_curve` style field, default 0 (= today's flat probabilities).
- **Entry:** new `theory/tension.py`; `generation.py` `_run_attempt`;
  [`chords.py`](../backend/app/generators/chords.py) `resolve_progression`/`_apply_substitution`
  (accept a probability scale); `quality.py` (optional dimension);
  [`arrangement.py`](../backend/app/core/arrangement.py) `SECTION_PROFILES` (tension targets
  live beside the existing per-type profiles).
- **Effort:** M.
- **Risk:** double-counting with `harmonic_boost` / section complexity scaling — tension
  scales *substitution choice*, not density, so they're orthogonal; verify by ear that
  bridges don't turn into chromatic soup (cap the scaled probability).
- **Done when:** plotted measured-tension curves for built songs peak at the bridge and
  relax at the outro (script + sweep), and verse 1 vs bridge substitution rates differ
  measurably; gate-off sweep byte-identical.

---

## Phase 12 — Polish (small, independent)

### 12.1 BPM-aware note density
- **Why:** density is per-beat regardless of tempo — the same style setting is frantic at
  170 BPM and empty at 70. Styles partially hide this because each style's `bpm_range` is
  narrow, but user tempo overrides and blends expose it.
- **Approach:** scale effective melody/arp density by `sqrt(ref_bpm / bpm)` where `ref_bpm`
  is the midpoint of the style's `bpm_range`; clamp to [0.7, 1.3]. Inside the style's own
  range the factor stays ≈ 1.0, so default generations barely move. Gate:
  `bpm_density_scaling` default false.
- **Entry:** `melody.py`, `arpeggio.py` (density computation); drums already scale
  hats by complexity — leave drums alone in v1.
- **Effort:** S.
- **Done when:** the same style at 0.5× and 1.5× of its reference BPM produces
  notes-per-*second* within ~20% of the reference rate (unit test on counts).

### 12.2 Motif extraction skips ornaments
- **Why:** `_melody_motif_intervals` ([`song_builder.py:72-90`](../backend/app/services/song_builder.py))
  takes the first 5 events by start time — grace notes (0.055 dur) and approach-run 16ths
  can pollute the "theme" that every chorus then develops.
- **Approach:** filter to events with `duration ≥ 0.2` before taking the first 5; same
  filter in `melody.py`'s internal motif lock and `answer.py`'s `melody_cell` if it reads
  raw events. No gate needed beyond a seed-stability note: this changes which motif some
  existing songs derive — acceptable, it's a correctness fix; call it out in the changelog.
- **Entry:** `song_builder.py`, `melody.py`, [`answer.py`](../backend/app/generators/answer.py).
- **Effort:** S.
- **Done when:** a unit test seeds a melody with a leading grace note and the extracted
  motif matches the ungraced line.

### 12.3 Drums hear the phrase plan
- **Why:** kick times feed chords/bass, but fills/crashes only know section boundaries
  (`section_end_bars`) — the drummer ignores the melody's phrase cadences, so a mid-section
  half cadence gets no punctuation.
- **Approach:** with 11.1's hoisted phrase plans available in `_run_attempt`, pass the
  phrase-boundary bars into `generate_drums`; at an *open*-cadence phrase boundary add a
  light setup (a short fill variant already in the fill vocabulary, lower intensity than
  section-end fills); at the section's climax phrase start, allow a crash. Gate:
  `phrase_aware_drums` default false.
- **Entry:** [`drums.py`](../backend/app/generators/drums.py) fills block (`~line 656`),
  `generation.py` (thread phrase bars).
- **Effort:** M.
- **Risk:** fill inflation — cap at one phrase-fill per 4 bars and keep section-end fills
  precedent (skip phrase fill when a section fill lands within 1 bar).
- **Done when:** in an opted-in style, fills land at phrase boundaries (test asserts fill
  onsets vs plan), and total fill count per section stays within +25% of baseline.

---

## Suggested sequence

1. ~~**Baseline sweep** → `docs/quality-baseline-v3.json`.~~ ✅ 2026-08-04.
2. ~~**10.1**~~ ✅ 2026-08-04 — then **10.2**; separate PRs, re-baseline after each.
3. **11.1 cadence harmony** (hoisting phrase plans also unblocks 12.3).
4. **11.4 targeted repair** — pays for itself immediately in search cost.
5. **11.2 goal-tone melody** — the flagship; migrate styles gradually.
6. **11.3 hook tiling** (stacks on 11.2), then **11.5 tension curve**.
7. **12.x** in any order, as palate cleansers between the L/M items.

## Measurement

- Per-dimension quality scores + attempts-per-green across all styles × fixed seeds,
  compared to `quality-baseline-v3.json` on every item
  (`scripts/quality_baseline.py --compare docs/quality-baseline-v3.json`).
- Byte-identical hash check on gated-off paths (and 4/4 for 10.2) every PR
  (add `--require-identical`; it exits 1 if any note moved).
- Ears: `/run-genregrid` A/B per style before flipping any style's gate on — the scorer
  measures agreement, only listening measures *music*.
