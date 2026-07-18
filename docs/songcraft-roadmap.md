# Songcraft Roadmap: From Correct to Composed

**Status:** plan — no code yet
**Context:** the correctness era is done (harmony agreement, instrument physics,
groove pocket, ensemble pushes, eight arrangement devices, pickups — all
measured and tested). What remains between "correct" and "a real song" is
**compositional intent**: the sense that one mind wrote every part from a
shared idea. This doc ranks the remaining gaps by how much song-ness each buys.

---

## Tier 1 — the "one composer" signals (highest payoff)

### A. Thematic unification: one cell, many parts
The single deepest difference between our output and a record. Real songs are
built from one or two short cells — the bass quotes the hook's rhythm, the arp
outlines the same shape, the counter-melody answers it. We already thread the
verse motif into the chorus melody, but the **bass, arpeggio, and
counter-melody invent their own material independently**.

Plan: extract a song-level *rhythmic cell* (2–4 onsets) and *melodic cell*
(2–4 scale-step intervals) from the first chorus hook (or the seeded motif) in
`_generate_song_sections`, and pass them to the other generators the way
`seed_motif` already flows into melody:
- **bass**: bias one pattern slot per 2 bars to echo the rhythmic cell's onsets
  (generic + 808 paths; walking bass exempt — it has its own language).
- **arpeggio**: start each phrase's contour with the melodic cell before
  free-running.
- **counter-melody**: already derived from the melody — verify it inherits the
  cell rather than smoothing it away.

Verify: new survey metric — *motif recurrence*: cross-correlation of onset
patterns between melody and bass/arp per section, expect a measurable rise.
Effort: the largest item here (touches three generators + threading), but it is
THE "composed, not assembled" feature.

### B. Antecedent/consequent phrase pairing (question → answer)
The strongest "written by a human" signal inside a melody: phrase 2 repeats
phrase 1's rhythm but ends differently (open cadence → closed cadence). The
phrase planner already assigns roles and open/closed cadences; what's missing
is that the consequent phrase **reuses the antecedent's rhythm**. Today each
phrase's rhythm is freshly sampled, so question/answer pairs don't sound
related.

Plan: in `generate_melody`, when a plan marks a phrase as answering its
predecessor, replay the predecessor's onset/duration skeleton and re-pitch it
(same mechanism as motif replay, extended to rhythm). Effort: medium, one file.

### C. Layer accumulation on section repeats
Real records escalate on every return: verse 2 carries something verse 1
didn't (a counter line, busier hats, the arp), chorus 2 > chorus 1. We
currently only *subtract* on repeats (thinned verse 2) and only escalate the
*final* chorus. The repeat of any section type should feel like "same place,
more happening."

Plan: extend `apply_arrangement_dynamics` (or the section part-mode logic)
with an accumulation policy: on a section type's second occurrence, add one
reserved layer (arpeggio into verse 2, pads into chorus 2 if held back from
chorus 1, denser hat pattern via a drums flag). Pairs naturally with the
existing thinned-v2 (strip the opening bars, then come back *bigger*).
Effort: medium; mostly arrangement-level, one drums flag.

---

## Tier 2 — transitions and endings (high noticeability per effort)

### D. Transition polish around the drop
- **Fill vs drop conflict**: boundary drum fills live in exactly the 2 beats
  the drop strips — when the drop fires we likely delete the fill it should
  replace. Audit; make it explicitly fill OR drop.
- **Snare-roll build** into the final chorus (16th roll, velocity crescendo,
  last bar) — the one build device we lack.
- **Crash guarantee** on the downbeat after any drop/stop (verify the drums
  generator already does this on section starts; add if not).
Effort: small each; do together.

### E. Endings: variety + the hook echo outro
Every song currently ends with the identical formula (tonic chord + bass +
kick/crash ring). The last impression a song makes should vary:
1. **ring-out** (current behavior),
2. **cold stop** (staccato final hit, no ring),
3. **hook echo** — the outro quotes a thinned fragment of the chorus hook with
   widening gaps, then the cadence.
Seeded per song like every other device. The hook-echo outro also fixes the
deeper issue that outros are currently fresh material — real outros look back.
Effort: small (1+2) / medium (3).

### F. Cross-section melody register continuity — TRIED, REVERTED
Each section's melody starts from its phrase-plan register, so section seams
can jump registers arbitrarily. The plan was to thread the previous section's
final melody pitch into the next section's starting register (same pattern as
`prev_voicing` for chords).

Implemented and measured (mean absolute pitch jump at section seams, 5 styles ×
12 seeds): it *regressed* seam smoothness — overall mean jump 3.90 → 4.40 st,
seams into cached repeats 3.33 → 4.34. The mechanism worked in isolation (a
higher previous pitch did open the next section higher), but at the song level
it lost to the existing architecture: HEAD already bounds seams by opening every
section from a consistent central register, while the type-theme **cached
repeats** (whose register F can't touch) and the **deliberate register plans**
(chorus lift, per-phrase targets) are register changes F shouldn't fight.
Seeding from a single — often octave-outlier — closing note just injected
variance; a median-of-closing-phrase signal was no better. The pickups already
bridge the *audible* seam. Reverted. Left here as a record so it isn't retried
blindly; a real fix would need to co-register cached repeats too, which fights
the chorus lift — not worth it.

---

## Tier 3 — polish (do opportunistically)

- **G. Breakdown final chorus**: modern pop's double-chorus — final chorus
  opens half-stripped (melody + claps), band re-enters at the midpoint.
  A ninth arrangement device; easy once C exists.
- **H. Pre-chorus micro-accel**: +1–2% tempo through the pre-chorus into the
  chorus push (tempo map already does the chorus side).
- **I. Mid-section micro-fills** — DONE. Audit found the `bar % 4 == 3` fill
  only fires for the 7 (of 31) styles with the `tom_fills` flag; the other 24
  repeat one groove verbatim through a whole section (the phrase-dynamics swell
  and hat-breath vary loudness, not rhythm). Added a subtle phrase-turn gesture
  (a ghost-snare pickup or a kick push) on the last bar of each *interior*
  4-bar phrase, gated to sections ≥ 8 bars and excluded from section-end bars
  (they get the real fill), intros/outros, and `tom_fills` styles (already
  filling — verified byte-identical). Interior phrase-turn activity rose ~40–70%
  for non-`tom_fills` styles; seeded/deterministic; cross-part survey metrics
  unchanged.

---

## Round 3 — inter-instrument call-and-response

### K. Answer the lead in its holes — DONE
The audit found the call-response *plumbing* already existed (`melody_rests`
threaded to chords/bass/arp) but every response was shallow: chords/arp just got
louder in the gap, the bass added a generic root→5th figure, and the
counter-melody could never fill a rest (it's a harmony line bound to melody
notes, present only on the final chorus). No voice played a *thematic answer*.
Measured landscape: ~8 answerable rests/song, concentrated in verses (median 2.0
beats) and intros/outros; choruses are the busiest and want the fewest answers.

Built a **layered** answer, both tiers seeded/deterministic and driven by the
song's melodic cell so the reply *relates* to the call (shared
`build_answer_phrase`: cell-contour walk landing on a chord tone, with a breath
before the lead re-enters):
- **Tier A (every build):** the bass rest-fill now traces the cell as a low echo
  instead of a generic root→5th (falls back to the old figure only before the
  cell exists). Lands on chord tones — survey metrics unchanged.
- **Tier B (when counter-melody is in the arrangement):** the counter-melody
  became dual-mode — harmonize the hook on the final chorus (unchanged) OR answer
  the lead's holes in verse/intro/outro with a distinct mid-register lick. The
  arrangement gate was relaxed so it survives into those sections.
- **Coordination:** when Tier B answers a section the bass floor stands down
  there (`melody_rests=None`) — verified 0 bass fills across 11 counter-melody-
  answered rests. The first verse (where the song cell doesn't exist yet) falls
  back to its own opening contour, lifting verse response coverage to ~53%.

Remaining (deliberate) gap: intros are `melodic` mode (chords+melody only), so
no voice is present to answer — left spacious by design.

---

## Measurement

Error metrics are near-zero and will stay the regression floor; song-ness needs
*structure* metrics in `survey_songs.py`:
- **motif recurrence** (A/B): onset-pattern correlation between melody phrases
  and between melody and bass/arp,
- **layer curve** (C): instrument-count-per-section should be non-decreasing
  across same-type repeats and peak at the final chorus,
- **transition coverage** (D/E): % of section boundaries carrying at least one
  device (fill, drop, pickup, build).

None of these are pass/fail — they let us see before/after movement the same
way clash% did. The final judge stays the same: ears in a DAW.

## Suggested order

1. **B** (phrase pairing) — one file, biggest melody win.
2. **C + D + E** (accumulation, transitions, endings) — one arrangement-layer
   session; all seeded devices with the established test pattern.
3. **A** (thematic unification) — the flagship; benefits from B/C landing
   first since the cell then propagates into already-paired phrases and
   accumulated layers.
4. **F, G, H, I** as follow-ups.
