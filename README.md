# GenreGrid

A style-based MIDI generator. Pick a genre, set your key, BPM, and complexity, and get back downloadable MIDI files for chords, bassline, melody, drums, arpeggio, pads, and counter-melody — all harmonically aligned to the same chord progression, as a single loop or a fully arranged song.

## Download

Grab the latest desktop app from the **[Releases page](https://github.com/TwDover/GenreGrid/releases/latest)** — no Python, Node, or terminal required. Download the file for your system, and the backend starts automatically when you open the app:

| Your system | Download |
|---|---|
| **Windows** | `GenreGrid Setup x.x.x.exe` (installer) |
| **macOS — Apple Silicon** (M1/M2/M3/M4) | `GenreGrid-x.x.x-arm64.dmg` |
| **macOS — Intel** | `GenreGrid-x.x.x-x64.dmg` |
| **Linux** | `GenreGrid-x.x.x.AppImage` (portable) or `.deb` |

> **macOS:** the app is currently **unsigned**, so the first time you open it macOS will warn about an unidentified developer. **Right-click the app → Open → Open**, or run `xattr -cr /Applications/GenreGrid.app`. You only need to do this once.

The Windows and Linux apps **auto-update**: when a new release is published, the app downloads it in the background and offers a restart. You can also check on demand with the **Updates** button in the app header. (macOS can't auto-update unsigned builds — Mac users grab new versions from the Releases page.)

Prefer to run from source or build it yourself? See [Running in the browser](#running-in-the-browser) and [Desktop app](#desktop-app-electron) below.

## What it does

- Generates MIDI for seven parts: **chords**, **bass**, **melody**, **drums**, **arpeggio**, **pads**, and **counter-melody**
- Each part is generated from a style definition (JSON) that controls BPM range, chord progressions, extensions, rhythm density, swing, humanization, and more
- Melody is chord-aware — targets chord tones on downbeats and uses context-aware note durations (longer notes on structural arrivals)
- **Phrase architecture** — a section's melody gets a *form* before any notes exist: each 4-bar phrase takes a role (statement, restatement, contrast, climax, resolution) from a form grammar (AABA, ABAC, …) that plans its contour peak, register, density, cadence, and motif restatement — so every section has exactly one high point and phrases that ask and answer
- Bass, chords, and melody share one harmonic grid — the same progression, resolved substitutions, and chords-per-bar timing — so the parts always agree on what chord is sounding
- Drums use genre-appropriate elements (kick patterns, ride, clap, crash, tom fills, swing) per style — and **arrange per section**: stripped intros, building pre-choruses, crash-announced choruses, half-time bridges, decaying outros, with fills sized by the energy of the next section
- **Loop mode** — generates a single tight section (the default) for a quick idea or a DAW-ready loop
- **Arrangement mode** — generates a full arrangement arc (intro → verse → chorus → outro) from a single bar count, with per-section complexity, dynamic scaling, and energy ramps at section transitions
- **Song Builder** — generates a complete song from named templates (Verse–Chorus, V–C–Bridge, Extended, Compact, Minimal) or a **custom template** you arrange yourself — including a **different style per section** (a lofi verse into a house chorus). Songs get real song craft: one shared progression across all sections, chord voicings that voice-lead across section seams, choruses that develop the verse's motif, an intro that teases the chorus hook, light variation on repeated sections, chorus/bridge key shifts plus a **final-chorus gear change**, pre-choruses that ramp harmonically into the drop, a tempo map (subtle chorus push + closing ritardando), and a proper ending bar that rings out on the tonic
- **Build a song around your melody** — drop a MIDI melody into the Song form: its key is auto-detected (Krumhansl-Schmuckler), a supporting chord progression is derived bar by bar, and your melody becomes the song's chorus hook — repeats, the intro tease, the counter-melody, and every section's motif development grow out of your idea
- **Per-section quality & re-roll** — every song section runs a quality-gated multi-attempt search; its score shows as a badge on the song timeline, and any section can be re-rolled with one click while the rest of the song stays byte-identical. Individual parts can also be re-rolled — or **added after the fact** if you forgot to select one
- **Version history** — every re-roll/add snapshots the song first; the History picker restores any of the last five states (and a restore is itself restorable)
- **In-app mixer** — a volume slider on every song part rebalances the stems on disk (preview, drag-to-DAW, and exports all reflect it); gains are absolute, so 100% always restores the generated balance
- **Note editing** — click a note in any song part's piano roll to select it, nudge with arrow keys (pitch ±1, Shift = octave, ←/→ = 16th-note steps), Delete to remove; saving rewrites the stem and rebuilds the song, with a version snapshot taken first so edits are undoable from History
- **Build automation** — pre-chorus sections carry a rising filter sweep (CC74 + half-depth CC1) on chords/pads and an expression crescendo (CC11) into the chorus, so builds sound produced, not just arranged
- **Songs survive reloads** — the recent-songs list reconciles with what's on disk at startup, so cleaned-up exports disappear and songs built in another session appear
- **Style blending** — blend a second style into a loop *or* a whole song (groove, swing, density, and progression pools interpolate)
- **DAW-ready song files** — `song.mid` carries section markers (Intro/Verse/Chorus… with key changes labeled) and a key signature, so your DAW timeline mirrors the app's
- **Style-aware playback** — in-browser preview uses genre-matched samplers and synthesis engines: acoustic kits, LinnDrum, breakbeats, Techno kit, Rhodes, clavinet, vibraphone, nylon guitar, accordion, strings, synth leads, and pads — routed automatically per style, with a **sidechain pump** on electronic styles (each kick ducks the mix so it breathes)
- **Quality scorer** — every generation is scored across up to six musical dimensions (harmonic coherence, part separation, rhythm fit, density, mix balance, and — when a learned corpus prior exists — style-match) and returns a 0–1 score, label, and any issue flags alongside the MIDI
- **Generation library** — high-scoring generations are saved locally and used to influence rhythm patterns in future generations, improving style consistency over time
- **Data-driven patterns** — each style ships with idiomatic chord progressions and drum patterns, so a fresh clone generates good output with no setup. An optional mining pipeline can further tailor generation from MIDI corpora **you supply** (e.g. Groove MIDI, POP909, Lakh — used locally under their own licenses; see [Training on real corpora](#training-on-real-corpora-optional)), toggled per generation with a **Use my local MIDI corpus** switch
- In-browser MIDI preview with play/stop, per-part mute (shift-click to solo), and a **seekable song timeline** with a live playhead and current-section highlight — click any section block to play from there; elapsed/total time shows in the playback bar, and actions confirm with toast notifications
- **WAV export** — offline-render the full mix or true per-part stems, matching the preview voices
- Generation history — last 10 results stay accessible in the UI
- **Drag to DAW** — in the desktop app, drag any part directly into your DAW using the drag handle on each part card
- **Reproducible seeds** — the same seed always rebuilds the same song, byte for byte, across app restarts

### Mix quality features

- Per-part velocity scaling, stereo panning (CC10), reverb send (CC91), and expression (CC11)
- Style-specific reverb depths — cinematic/ambient styles get more room; tight electronic styles stay dry
- Chord voice balancing — bass note grounded, inner voices recede, soprano present
- Melody register ceiling — chord voicings are automatically capped below the melody's lowest note
- Sustain pedal (CC64) applied only to pad/hold styles; suppressed for staccato comping and orchestral brass/strings
- Phrase breath dynamics — 4-bar arc of subtle velocity swells across all melodic parts
- Arpeggio call-and-response — boosts arpeggio velocity during melody rests; reduces arpeggio complexity when melody is active
- Section energy ramps — gradual velocity fade-in over the first 8 beats of any energy-increasing transition (verse → chorus, intro → verse), including across Song Builder section seams
- Kick-sync chord comping — chord hits that land within an 8th-note of a kick drum receive a small velocity accent
- Pads sit as a soft, voice-led wash above the comp (choruses/bridges only in songs); the counter-melody harmonizes the lead a diatonic 3rd/6th below, reserved for the final chorus so the ending outsizes what came before

---

## Styles

31 built-in styles across electronic, hip-hop, live/band, global, and mood categories — the style browser filters by category, pins favorites, and **auditions any style with one click** (generates and plays a 2-bar taste):

`lofi` `boom_bap` `dark_trap` `drill` `grime` `trap_soul` `cloud_rap` `hyperpop`
`house` `techno` `drum_and_bass` `synthwave` `future_bass` `jersey_club`
`jazz` `latin_jazz` `bossa_nova` `soul` `rnb` `funk`
`afrobeats` `afropop` `samba` `cumbia` `reggaeton` `dancehall` `baile_funk`
`cinematic` `epic_orchestral` `ambient` `dark_ambient`

---

## Song Builder templates

| Template | Bars* | Structure |
|---|---|---|
| **Verse–Chorus** | 56 | Melodic intro · Verse×2 · Chorus×2 · Melodic outro |
| **V–C–Bridge** | 80 | No-drum intro · Verse×2 · Pre-chorus×2 · Chorus×2 · Bridge · Final chorus · Melodic outro |
| **Extended** | 80 | Foundation intro · Verse×2 · Chorus×2 · Instrumental · Bridge · Final chorus |
| **Compact** | 40 | Chords intro · Verse×2 · Chorus×2 · Chords outro |
| **Minimal** | 24 | Foundation intro · Main (16 bars) · Melodic outro |
| **Custom** | — | Arrange your own section sequence (type + bars + optional per-section style) in the Song form |

\* Every song gets one extra **ending bar** (held tonic chord + crash, with a ritardando) on top of the listed total.

Verse sections are 16 bars in all mainstream templates (Verse–Chorus, V–C–Bridge, Extended). Chorus sections are 8 bars. Bridges modulate to the subdominant by default; the last chorus adds a configurable **final lift** (+1 semitone by default) on top of any chorus key shift.

### Build around your melody

Drop a `.mid` file into the **Build around my melody** field in the Song form and the builder composes the song around it:

- The **most melody-like track** is picked from the file (non-percussion, highest average pitch among tracks with a real note count)
- Key and mode are **auto-detected** (Krumhansl-Schmuckler pitch-class correlation) — the form's key/scale are ignored, and the song's BPM comes from the file
- A supporting **chord progression is derived by Viterbi decoding** over the diatonic chord vocabulary — per-bar melody coverage plus functional-motion rewards (V→i, IV→V, …), ending on a chord that pulls back to the loop's top — and that progression drives the whole song
- Your melody becomes the **chorus hook**: chorus repeats, the intro tease, the counter-melody, and every section's motif development all grow out of it

Current assumptions: 4/4 time, and the hook is looped or trimmed to fit the chorus length. Re-rolling parts or sections of an imported song keeps your melody intact.

---

## Stack

- **Backend** — Python, FastAPI, [mido](https://mido.readthedocs.io/)
- **Frontend** — Vue 3, TypeScript, Vite, [Tone.js](https://tonejs.github.io/), [@tonejs/midi](https://github.com/Tonejs/Midi)
- **Desktop** — Electron (Windows, macOS & Linux), with auto-update via [electron-updater](https://www.electron.build/auto-update) on Windows/Linux

---

## Running in the browser

### Requirements

- Python 3.11+
- Node.js 20+ (CI builds and releases on Node 22)

### Just run the app — one command

Builds the frontend once, starts the backend, serves the app at `http://localhost:4173`, and opens your browser. Ctrl+C stops everything. First run creates the venv and installs all dependencies automatically; later runs reuse the build (pass `--rebuild` / `-Rebuild` after pulling changes).

**Windows**
```powershell
.\start.ps1
```

**Linux / macOS**
```bash
./start.sh
```

### Develop — one command

Same idea but with live reload on both sides: backend (`:8000`, uvicorn `--reload`) and frontend (`:5173`, Vite dev server with HMR). Use this when editing code.

**Windows**
```powershell
.\dev.ps1
```

**Linux / macOS**
```bash
./dev.sh
```

Prefer separate terminals? The manual steps:

### Backend

**Windows**
```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**Linux / macOS**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The UI runs at `http://localhost:5173`. Run both in separate terminals.

---

## Desktop app (Electron)

The desktop app bundles the backend into a self-contained executable — no Python or terminal required to run it.

> **Important:** PyInstaller must be run on the same OS you are building for. To produce a Windows `.exe`, build on Windows. To produce a Linux `.deb` / AppImage, build on Linux. To produce a macOS `.dmg`, build on a Mac.

Every platform is a one-command build. Each script creates a Python venv if needed, installs dependencies, compiles the backend with PyInstaller, type-checks the frontend, and packages the Electron app. First runs take a few minutes; later runs reuse the venv. Add `--clean` (or `-Clean` on Windows) to wipe previous build artefacts first.

### Build (Linux / macOS — one command)

```bash
./build.sh
```

**Output** — Linux: `frontend/release/GenreGrid-x.x.x.AppImage` and `genregrid_x.x.x_amd64.deb` · macOS: `frontend/release/GenreGrid-x.x.x-<arch>.dmg` and `.zip` (unsigned; the script sets `CSC_IDENTITY_AUTO_DISCOVERY=false` for you)

### Build (Windows — one command)

```powershell
.\build.ps1
```

**Output** — `frontend/release/win-unpacked/GenreGrid.exe` (portable) and `frontend/release/GenreGrid Setup x.x.x.exe` (installer)

### Running on Windows

Launch `frontend/release/win-unpacked/GenreGrid.exe` directly, or run the NSIS installer. The backend starts automatically — no separate terminal needed.

### Running on Linux

**AppImage** (portable, no install):
```bash
chmod +x "frontend/release/GenreGrid-x.x.x.AppImage"
./frontend/release/GenreGrid-x.x.x.AppImage
```

**Debian/Ubuntu package**:
```bash
sudo dpkg -i frontend/release/genregrid_x.x.x_amd64.deb
# Then launch GenreGrid from your application menu
```

### Running on macOS

Open the `.dmg` and drag **GenreGrid** to Applications, then launch it. The backend starts automatically. Choose the build matching your Mac: `-arm64` for Apple Silicon (M1/M2/M3/M4), `-x64` for Intel.

Because the app is **unsigned** (no Apple Developer certificate), Gatekeeper blocks it on first launch. Bypass it once:

- **Right-click** (or Control-click) **GenreGrid.app → Open → Open**, or
- run `xattr -cr /Applications/GenreGrid.app` in Terminal.

### Drag to DAW

Each part card has a **⠿ drag handle**. Once a generation is ready, drag the handle directly into your DAW's track area to drop the `.mid` file. The handle dims briefly while the file is being prepared, then becomes fully opaque when ready to drag.

### User data

The desktop app stores exports and the generation library in:

- **Windows:** `%APPDATA%\genregrid-frontend\backend-data\`
- **macOS:** `~/Library/Application Support/genregrid-frontend/backend-data/`
- **Linux:** `~/.config/genregrid-frontend/backend-data/`

---

## Releasing (maintainers)

You **do not need a Mac, a PC, and a Linux box** to ship all three builds — GitHub Actions ([`.github/workflows/build.yml`](.github/workflows/build.yml)) builds every platform in the cloud and publishes them to a downloadable **GitHub Release**.

To cut a release:

```bash
# 1. Bump the version in frontend/package.json (e.g. 0.1.0 -> 0.2.0), commit it.
# 2. Tag and push the tag:
git tag v0.2.0
git push origin v0.2.0
```

> **Keep the tag and the version in sync.** The `version` field in [`frontend/package.json`](frontend/package.json) sets the installer **filenames** (`GenreGrid-0.2.0-arm64.dmg`), while the git **tag** sets the Release name. Tag `v0.2.0` must match version `0.2.0`, or the Release will be titled `v0.2.0` but contain files named `...0.1.0...`. The tag is the trigger — editing `package.json` alone publishes nothing.

> **Auto-update depends on the release assets.** Alongside the installers, CI uploads `latest.yml` (Windows) and `latest-linux.yml` — installed apps poll these to discover new versions. Don't delete them from a Release, or auto-update silently stops finding updates. The build scripts pass `--publish never` to electron-builder; the CI `release` job is the only thing that uploads to GitHub.

The tag (`v*`) triggers four parallel build jobs — Linux, Windows, macOS arm64, macOS Intel — and, once they all pass, a `release` job that attaches every installer (`.exe`, `.dmg`, `.AppImage`, `.deb`, `.zip`) to a new Release with auto-generated notes. Users then download from the [Releases page](https://github.com/TwDover/GenreGrid/releases/latest). Pushes to `main` and pull requests still build and type-check every platform, but only **tags** produce a published release.

> **Note:** macOS builds are **unsigned** (see [Running on macOS](#running-on-macos)). To ship notarized, warning-free Mac apps you'd need an Apple Developer account and would add the signing certificate + `APPLE_ID`/`APPLE_APP_SPECIFIC_PASSWORD` as GitHub Actions secrets. Optional — the unsigned builds work, users just accept the first-launch prompt.

---

## Training on real corpora (optional)

GenreGrid's generators are **data-driven**. Each style ships with generic, idiomatic chord progressions and drum patterns baked into its JSON, so a fresh clone already generates good output with no setup. For deeper, genre-specific behaviour you can mine MIDI corpora yourself — the mined statistics then bias progression, melody, and drum generation at runtime. Corpora are used **locally, on your machine**, under their own licenses; nothing from them is redistributed in this repository.

### How it works

- **Harmony & melody** — `scripts/mine_corpus.py` reads a folder of MIDI and writes a per-genre **prior** (chord-progression n-grams, 4-bar loops, melodic interval/rhythm histograms) to `backend/app/priors/<name>.json`.
- **Drums** — `scripts/mine_grooves.py` mines the Groove MIDI Dataset into per-genre drum grooves (kick/snare/hat placement, velocity, swing, fills) at `backend/app/priors/grooves/<name>.json`.
- A style draws from a prior via its `"prior"` field (or its `id`) and a groove via its `"groove"` field (or `id`). Priors are **git-ignored** — a fresh clone contains none, and generation falls back to the baked-in patterns.
- The built-in (baked-in) style patterns are **always** applied. The **Use my local MIDI corpus** toggle (request flag `use_priors`) *additionally* overlays your mined priors on top. It only appears for styles that have a prior present, and is **off by default in the UI** — an opt-in, since you're responsible for your corpus's license.

### Mine a corpus

```bash
cd backend && source .venv/bin/activate

# Harmony/melody from a genre folder (e.g. POP909 → "pop")
python ../scripts/mine_corpus.py ~/datasets/pop909 pop

# Drums from the Groove MIDI Dataset
python ../scripts/mine_grooves.py ~/datasets/groove

# (Lakh only) bucket LMD-matched into genre folders first, using tagtraum labels,
# then mine each folder with mine_corpus.py
python ../scripts/filter_lakh_genres.py \
    --lmd ~/Downloads/lmd_matched \
    --cls ~/Downloads/msd_tagtraum_cd2.cls \
    --out ~/Downloads/lakh_by_genre
```

Use `--limit N` on `mine_corpus.py` to sample large genre folders. Re-running a script refreshes its prior; restart the backend to pick it up.

> **Data & licensing** — the mining scripts run locally and ship no music. **You** are responsible for obtaining each dataset legitimately and complying with its license. See [DATA_LICENSES.md](DATA_LICENSES.md).

---

## Adding a style

Create a JSON file in `backend/app/styles/` — it will be picked up automatically. See an existing style like `lofi.json` for the full schema.

Key fields:

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique identifier matching the filename |
| `name` | string | Display name |
| `bpm_range` | `[min, max]` | Suggested tempo range |
| `default_scale` | string | `major`, `minor`, or any mode in `constants.py` |
| `preferred_keys` | list | Root notes this style favours |
| `progression_templates` | list of lists | Roman numeral progressions to pick from |
| `chord_extensions` | object | `allow_7th` and `allow_9th` probabilities (0–1) |
| `chord_register` | `[low, high]` | MIDI note range for chord voicings (default `[48, 72]`) |
| `comp_style` | string | Optional comping pattern: `jazz_comp`, `bossa_comp`, `funk_stab`, `lofi_strum`, `pad_hold`, `house_stab`, `synth_gate` |
| `chord_rhythm` | list | 16-step binary rhythm for chord hits (alternative to `comp_style`) |
| `staccato_factor` | float | Shorten chord durations (0.0–1.0); useful for stab styles |
| `open_voicing_prob` | float | Probability of dropping an inner chord voice |
| `drop_2_prob` | float | Probability of applying Drop-2 voicing |
| `turnaround_prob` | float | Probability of ii-V turnaround on the last chord of each 4-bar phrase |
| `bass` | object | `pattern_density`, `octave_jumps`, `sustain_bias`, optional `bass_style` (`walking`, `808`, `standard`) |
| `arpeggio` | object | `pattern` (`up`/`down`/`up_down`/`random`/`chord_burst`), `speed` (beats per note), `include_octave`, `allow_7th` |
| `melody` | object | `density`, `stepwise_motion`, `leap_probability`, `rest_probability`, `range [lo, hi]` |
| `melody_scale` | string | Scale used for the melodic contour (can differ from harmony, e.g. pentatonic over diatonic chords; chord-tone targeting always uses the harmonic scale) |
| `pads` | object | Optional pads-part config: `register [lo, hi]` (default `[64, 86]`), `velocity`, `color_9th_prob` |
| `counter_melody` | object | Optional counter-melody config: `velocity_scale` (default 0.72), `floor` (lowest harmonized note, default 55) |
| `drums` | object | `hat_density`, `triplet_probability`, `snare_standard_beats`, `swing`, optional `kick_pattern`, `hat_pattern`, `hat_vel`, `use_ride`, `use_clap`, `crash_on_bar_1`, `flam_prob`, `tom_fills`, `half_time_bridge` (default true — bridges flip to half-time in songs) |
| `velocity_base` | int | Base MIDI velocity for chord notes |
| `vel_arc_start` | float | Velocity at bar 1 relative to peak (0.0–1.0); controls the dynamic build across the section |
| `groove_push` | float | Systematic timing offset in beats (negative = behind beat, positive = ahead) |
| `secondary_dominants` | bool | Allow secondary dominant substitutions in progressions |
| `tritone_substitution` | bool | Allow tritone substitutions on V chords |
| `chorus_key_shift` | int | Semitones to transpose the key for chorus sections in Song Builder |
| `bridge_key_shift` | int | Semitones to transpose bridge sections (default 5 — subdominant lift) |
| `final_chorus_lift` | int | Extra semitones added to the LAST chorus only (gear change; default 1) |
| `prior` | string | Name of a mined harmony prior to bias progressions/melody (defaults to `id`); optional — see [Training](#training-on-real-corpora-optional) |
| `groove` | string | Name of a mined drum groove to overlay (defaults to `id`); optional |

To add style-aware **playback instruments**, update the mapping dicts in:
- `frontend/src/soundfonts/melodic.ts` — chords/melody/arpeggio instrument
- `frontend/src/soundfonts/bass.ts` — bass instrument
- `frontend/src/soundfonts/drums.ts` — drum kit
- `frontend/src/composables/useMidiPlayer.ts` — add to `SYNTH_STYLES`, `MELODIC_SYNTH_STYLES`, or `PAD_STYLES` if the style uses synthesis rather than samples

The **pads** and **counter-melody** parts always play through dedicated voices (a sustained pad wash and a soft string ensemble) regardless of style, so they don't need per-style mapping.

---

## Running tests

**Backend (Windows)**
```powershell
cd backend
.venv\Scripts\activate
pytest
```

**Backend (Linux / macOS)**
```bash
cd backend
source .venv/bin/activate
pytest
```

**Frontend**
```bash
cd frontend
npm test              # vitest
npx vue-tsc --noEmit  # type-check
```

CI runs both suites (plus the type-check) on every push and pull request.

---

## License

GenreGrid is free software licensed under the **GNU General Public License v3.0** — see [LICENSE](LICENSE).

```
Copyright (C) 2026 Tw Dover

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. This program is distributed WITHOUT ANY WARRANTY; without even the
implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
the GNU General Public License for more details.
```

### Data & corpora

The GPL covers the **code**. Training/research datasets and any priors you mine
from them are governed separately — the repository ships **no dataset and no
mined priors**, and the mining scripts run locally. See [DATA_LICENSES.md](DATA_LICENSES.md)
for dataset licenses, attribution (e.g. Groove MIDI is CC-BY 4.0), and the
data-free policy.
