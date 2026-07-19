# Quality Roadmap 2: From Composed to Produced

**Status:** plan — no code yet
**Context:** the songcraft roadmap is complete (thematic cells, phrase pairing,
layer accumulation, ending variety, call-and-response, micro-fills all landed
and measured). Songs now hold together structurally. What remains splits into
three axes: **feel** (the humanization layer is a generation behind everything
above it), **idiom** (guitar genres need riff-first architecture; harmony needs
chromatic color), and **workflow** (the user can steer everything except the
harmony and can't protect parts they like). This doc ranks the work by payoff.

Conventions carried over from roadmap 1: every new device is seeded and
deterministic per song, gated so untouched styles produce byte-identical
output, and lands with a before/after metric in `scripts/survey_songs.py`.
The final judge stays the same: ears in a DAW.

---

## Tier 1 — biggest audible payoff

### 1. Groove realism: mined feel profiles replace uniform jitter
`services/humanize.py` is the weakest layer relative to what sits on top of
it: `humanize_timing` is `random.uniform(±ticks)` and velocity is base ±
random. Real feel is *systematic*, not random — bass sits 5–15 ms behind the
kick, hats push ahead, backbeats land late in laid-back styles, and a
drummer's velocity contour across a 16th-note bar is a repeating shape.

Plan:
- Extend the mining pipeline (`mining/drums.py` — `analyze_drum_song`,
  `finalize_groove`, `derive_drum_fields`) to also extract per-style **feel
  templates**: median timing offset and median velocity per 16th-note slot,
  per instrument class (kick / snare / hat / other), from the same corpora the
  groove miner already reads.
- Add a `feel` block to the style schema (16 timing offsets + 16 velocity
  factors per instrument class). Ship hand-authored defaults for every style
  so a fresh clone benefits without any corpus; mined values overwrite them
  when the user runs `scripts/mine_grooves.py`.
- In `humanize.py`, apply the template as the *baseline* offset for a note's
  slot and shrink the existing random jitter to a small residual on top
  (roughly a third of today's spread). Add per-part lag constants (bass
  behind kick, hats ahead) threaded the same way `groove_push` already is.
- Deterministic: seed the residual RNG from the song seed like every other
  device.

Verify: new survey metric — *timing signature*: per-slot mean offset of
generated drums/bass should be non-zero and stable across seeds for styles
with a feel block, and unchanged (byte-identical) for styles without one.
A/B render lofi, boom_bap, funk (feel-heavy styles) in a DAW.
Effort: large (mining + schema + humanize + threading), but this is THE
"MIDI demo → produced track" gap.

### 2. Riff mode for guitar genres
Metal/rock/doom currently use the universal architecture: comped chords +
melody on top. Those genres are *riff-first* — identity lives in a 1–2 bar
low-register figure, guitar and bass in unison, palm-muted pedal-tone chugs
alternating with power-chord stabs; sung melody matters mostly in the chorus.

Plan:
- New comp mode `riff` in `generators/chords.py` (alongside the
  `_COMP_RHYTHMS` styles like `palm_mute` / `rock_drive`): instead of comping
  the progression, emit a riff — built from the song's rhythmic cell, pitched
  on the chord root's pedal tone with power-chord stabs on cell accents,
  chromatic/scale approach notes allowed on the last 8th of the bar.
- The riff is a **song-level object**: generate it once per song (seeded),
  transpose it through the progression, vary it per section the way comp
  section variants already do (`comp_section_variants`: half-time crush for
  doom intros, opened-up stabs for choruses).
- Bass doubles the riff an octave down in riff sections (new branch in
  `generators/bass.py`, same pattern as the existing 808/generic split).
- Melody stands down in riff verses (density floor, or tacet with the
  counter-melody answer gate widened) and returns for choruses/leads.
- Opt-in per style: `"comp_style": "riff"` for metal, doom_metal, rock;
  everything else byte-identical.

Verify: survey — melody/bass onset correlation should spike in riff sections
(bass doubles guitar); DAW listen against reference riffs. Reuse the motif
recurrence metric from roadmap 1.
Effort: large-medium. The flagship for the genre-expansion direction.

### 3. Hook memorability as a scored dimension
`services/quality.py` scores correctness (coherence, separation, rhythm fit,
density, mix, style-match) — nothing measures "is it catchy." A hook is
catchy when it's *compressible*: few distinct pitches, a repeated rhythmic
figure, one surprise.

Plan:
- New `_hook_score` in `quality.py`, chorus-melody only: (a) onset-pattern
  self-similarity between the chorus's bars (autocorrelation), (b) distinct
  pitch-class count penalty outside a 3–6 sweet spot, (c) motif repetition
  ratio (share of notes belonging to a repeated interval n-gram).
- Weight it into `score_generation` **only for chorus sections** so the
  existing multi-attempt search starts hunting memorable choruses, not merely
  valid ones. Report it as its own dimension in the score payload so the
  frontend badge tooltip can show it.
- Calibrate thresholds against the corpus miners' POP909 hooks before wiring
  it into the gate (write a tiny calibration script under `scripts/`).

Verify: distribution of hook scores over 5 styles × 12 seeds before/after
gating; confirm the search converges (attempt counts don't explode — cap
unchanged). No regression in the other five dimensions.
Effort: small-medium, one file plus a calibration script. Do this early —
it multiplies the value of every re-roll.

---

## Tier 2 — harmony depth

### 4. Harmonic color: borrowed chords and secondary dominants
Progressions come from per-style template pools plus extensions. Missing:
the chromatic seasoning real progressions use — a secondary dominant (V/x)
before a diatonic target, borrowed iv or ♭VII in major, ♭VI in the darker
minor styles.

Plan:
- In `theory/chords.py`, add a substitution pass that runs after progression
  selection: with per-style probability (`chromatic_color` field, default 0 =
  byte-identical), replace at most **one** chord per 4-bar phrase with a
  correctly-resolved color chord (V/x only where x follows; borrowed chords
  only on weak bars; never the final cadence bar).
- The scorer's `_harmonic_coherence` must learn these are legal: pass the
  resolved (post-substitution) chord map, which the shared harmonic grid
  already threads to all parts — melody/bass will follow automatically.
- Enable at low probability for jazz, soul, rnb, latin_jazz, bossa_nova,
  cinematic first; leave electronic styles at 0.

Verify: coherence score unchanged (the grid keeps parts agreeing); flag rate
for "non-diatonic" issues stays zero; DAW listen for the resolution.
Effort: medium, mostly one theory file + style flags.

### 5. Bridge-escape device
Bridge key shifts exist (`bridge_key_shift`, subdominant default), but the
bridge still draws from the same progression pool as everything else. Real
bridges start somewhere the song hasn't been and walk home.

Plan: small bridge-progression grammar in the song path
(`routes_song.py` where `bridge_key_shift` is applied): open on an unused
diatonic chord (vi if the song is I-heavy, ♭VI as deceptive option in minor),
2–3 bars of departure, then a dominant-pedal bar into the returning section.
Seeded choice between "new-chord bridge" and current behavior so half of
songs keep today's sound.

Verify: transition-coverage metric from roadmap 1 unchanged; new check that
the bridge's first chord ∉ verse/chorus chord set when the device fires.
Effort: small-medium. Pairs naturally with 4.

---

## Tier 3 — workflow / ease of use

### 6. Progression choose-and-lock
Harmony is the one core decision the user can't touch. Plan:
- API: expose the resolved progression (Roman numerals + concrete chords per
  bar) in the generation/song response; accept an optional
  `progression_override` on generate/re-roll that bypasses pool selection
  (validated against the key).
- UI: progression strip on the song result (chips per bar, Roman numeral +
  chord name, cadence label on phrase ends); "edit" opens a picker seeded
  with the style's pool plus manual entry; a **lock** toggle pins it across
  section re-rolls (thread through the existing regen path next to
  `regen_salt`).
- Doubles as a theory-learning surface — label cadences and any Tier-2 color
  chords ("V/vi — secondary dominant").

Effort: medium (API small, UI the bulk). Highest-value workflow item.

### 7. Compare-and-keep re-rolls
The quality search already generates candidates internally; re-roll replaces
in place. Plan: "Roll ×3" on a section/part — backend returns the top 3
scored candidates (they exist inside the multi-attempt loop; persist instead
of discarding), frontend shows three mini piano-roll cards with play buttons,
user keeps one, others deleted. History snapshot before commit, as today.
Effort: medium; mostly plumbing candidate persistence + a picker UI.

### 8. Part locking
"Lock this bass line": per-part lock flags on a song section; a section
re-roll regenerates only unlocked parts, reusing the locked stems and the
cached progression/grid so everything still agrees. Backend already re-rolls
single parts (`regen_part`) — this is the inverse gate. Locked parts shown
with a padlock on the part card; note-edited parts auto-lock.
Effort: small-medium. Complements 7 nicely.

### 9. User taste feeds the library
`services/library.py` learns only from the scorer (`save_generation` gated on
score). Plan: two implicit/explicit signals — (a) any export/download counts
as a keep (implicit positive, no UI), (b) a thumbs-up on the quality badge
saves to the library regardless of score, thumbs-down excludes that
generation's patterns. `_get_learned_patterns` then weights user-kept
generations 2–3× over merely high-scoring ones.
Effort: small. Makes the priors learn the *user's* taste, not the scorer's.

### 10. DJ intro/outro option
For electronic styles (house, techno, drum_and_bass, jersey_club, baile_funk):
a Song-form toggle that prepends/appends an 8-bar beat-only mixable section
(drums + bass only, no melodic content, no fills in the last bar) outside the
arrangement arc. Section marker "DJ Intro"/"DJ Outro" in `song.mid`.
Effort: small. Makes club-style exports actually mixable.

---

## Measurement

New survey metrics to add to `scripts/survey_songs.py` alongside roadmap 1's:
- **timing signature** (1): per-slot offset profile present + stable per style,
- **riff unison** (2): melody-register emptiness + bass/guitar onset
  correlation in riff sections,
- **hook score distribution** (3): median and spread per style, before/after,
- **color-chord legality** (4): substituted chords resolve as specified,
  zero coherence regressions,
- **lock fidelity** (7/8): locked stems byte-identical across re-rolls.

## Suggested order

1. **3** (hook score) — small, immediately multiplies every quality-gated
   search and re-roll that follows.
2. **1** (feel profiles) — largest audible win; start with hand-authored
   defaults, mine later.
3. **2** (riff mode) — the genre-expansion flagship; benefits from 1 landing
   first (palm-mute chugs need the tightened feel layer).
4. **6 + 8** (progression lock, part lock) — one workflow session; both
   thread through the same regen path.
5. **4 + 5** (harmonic color, bridge escape) — one harmony session.
6. **7, 9, 10** opportunistically — each is self-contained.
