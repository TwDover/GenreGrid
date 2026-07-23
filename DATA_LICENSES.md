# Data, corpora, and licensing

GenreGrid's **code** is licensed under **GPL-3.0** (see [LICENSE](LICENSE)).

This document covers the separate question of **training/research data**. Read it
before mining a corpus or committing any generated artifacts.

## What this repository ships

- **Source code only.** No MIDI datasets and no mined priors are committed.
- The corpus-mining scripts (`scripts/mine_corpus.py`, `scripts/mine_grooves.py`,
  and the `scripts/filter_lakh_genres.py` pre-processor, which only **symlinks**
  files you already have) run **on your machine** against datasets **you** obtain,
  and write priors to `backend/app/priors/` — which is **git-ignored**. A fresh
  clone therefore contains no third-party data; the generators fall back to their
  built-in templates and baked-in patterns until you mine a corpus locally.

## What the mining produces (and why it's low-risk)

The pipeline extracts **aggregate statistics** — chord-progression n-gram counts,
melodic interval histograms, and per-step drum-hit probabilities across a whole
corpus. These priors **cannot reproduce any source recording**; they are counts,
much closer to unprotectable facts than to a copy of any work. Even so, we keep
them out of the repo so there is no question of redistributing anything derived
from third-party datasets.

**What the committed style definitions contain.** The style JSONs in
`backend/app/styles/` carry only **generic, non-copyrightable musical patterns** —
common chord progressions (e.g. `I–V–vi–IV`) and drum-hit patterns — not dataset
content. Chord progressions and rhythmic patterns are unprotectable musical
building blocks, so these ship freely regardless of what corpus (if any) informed
them. No prior file, and nothing traceable to a specific third-party dataset, is
committed.

## If you mine a corpus

You are responsible for complying with that dataset's license. Quick reference
(**verify each dataset's own LICENSE — this table is guidance, not legal advice**):

| Dataset | License | Notes |
|---|---|---|
| **Groove MIDI Dataset** (drums) | **CC-BY 4.0** | Cleanest. Original drummer performances (not song transcriptions). Commercial use OK **with attribution** (below). |
| **POP909** (pop melody+chords) | Research/academic use | MIDIs are transcriptions of copyrighted songs. Mine locally; do not redistribute. |
| **Lakh MIDI Dataset** | Provided for research | Underlying songs are copyrighted. Mine locally; do not redistribute. |
| **MetaMIDI Dataset** | Research license (registration) | Same posture as Lakh. |
| **MAESTRO** | **CC-BY-NC-SA 4.0** | **Non-commercial.** Avoid if you intend commercial use. |
| **Weimar Jazz Database** | See their terms | Verify commercial/NC status before shipping anything derived from it. |
| **Nottingham / folk** | Public domain / permissive | Clean. |
| **JSB Chorales** (Bach) | Public domain | Compositions are public domain. |

**Rule of thumb:** derive statistics locally from any of these; only *ship*
artifacts derived from permissively-licensed (CC-BY, public-domain) sources, and
**never** commit the raw `.mid` files.

## Attribution (for CC-BY sources you choose to ship)

- **Groove MIDI Dataset** — Gillick, Roberts, Engel, Eck, Bahdanau; Google Magenta,
  2019. Licensed CC-BY 4.0. https://magenta.tensorflow.org/datasets/groove
- **Salamander Grand Piano** — Alexander Holm. Licensed CC-BY 3.0. The piano sample
  set bundled at `frontend/public/samples/piano/` (the Tone.js-hosted subset) is
  derived from this work. https://archive.org/details/SalamanderGrandPianoV3

## Bundled instrument samples (`frontend/public/samples/`)

These are the audio one-shots the app plays. Samples are **data**, licensed
separately from the GPL-3.0 code. **Everything shipped now has a confirmed license:**

| Set | Source | License | Notes |
|---|---|---|---|
| **Piano** (`piano/`) | Salamander Grand Piano (Alexander Holm) | **CC-BY 3.0** | Attributed above. Clean to ship. |
| **Vibraphone** (`melodic/vibraphone/`) | **VCSL** — Versilian Community Sample Library | **CC0 / public domain** | Velocity-layered (soft/hard mallets) via `scripts/build_velocity_samples.py`. No attribution required; kept here as courtesy. https://github.com/sgossner/VCSL |

Every other instrument is **synthesized** in the app (no shipped samples), so there is
nothing else to license. A **Samples / Synth toggle** in the transport bar switches
between the sampled voices above and full synthesis.

> **Removed for licensing (2026-07-23).** The following sets were deleted because their
> redistribution rights were **not confirmed** — see `docs/LICENSE_AUDIT.md`:
> - **MusyngKite** (all `bass/` + 7 `melodic/` voices: electric pianos, clavinet,
>   accordion, drawbar organ, nylon guitar, string ensemble). The redistributor labels
>   it CC-BY-SA 3.0, but the soundfont's original author says it is "free to use but
>   **not meant to be redistributed**… or used for commercial purposes." Those voices
>   now synthesize.
> - **Tone.js drum samples** (`drums/`). No LICENSE on the source repo; and the app
>   already synthesizes its drum kit, so the samples were unused. Deleted.
>
> **Adding samples back cleanly:** use `scripts/build_velocity_samples.py` with a
> confirmed **CC0 / public-domain** (VCSL) or **CC-BY** (with attribution) source only.
> Note that University of Iowa MIS, despite being widely called "free," carries **no
> explicit license grant**, so it is *not* used here. VCSL is acoustic/orchestral and
> does not cover the electric/synth voices, which is why they remain synthesized.

## Note on the GPL and data

The GPL-3.0 covers this project's source code. It does **not** attempt to license
any dataset you mine, nor the statistical priors you generate locally — those are
governed by the respective dataset licenses above. Keeping the repo data-free
avoids mixing the two.

## Disclaimer of responsibility

The mining scripts are **tools**. They ship no music, and they do not copy,
embed, upload, or redistribute any dataset — they read data that already exists
on your machine and produce local aggregate statistics (and, for
`filter_lakh_genres.py`, symlinks).

**You are solely responsible** for how you use them, including:

- obtaining every dataset legitimately and complying with its license and terms;
- ensuring you have the right to analyze the material in your jurisdiction;
- not redistributing the source files or any artifact that reproduces them.

The software is provided **WITHOUT ANY WARRANTY** (see the GPL header in each
file). To the maximum extent permitted by law, the GenreGrid authors and
contributors accept **no liability** for any use of these tools, including any
use to process material you are not authorized to use. GenreGrid is **not
affiliated with, and grants no rights to,** any third-party dataset or its
rights-holders. Using these scripts on copyrighted material without permission
is **your** responsibility, not the project's.

*This document is informational and not legal advice. If you plan to distribute
mined priors or use GenreGrid commercially, review each dataset's license and
consider professional counsel.*
