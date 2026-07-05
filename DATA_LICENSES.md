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
