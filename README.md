# GenreGrid

A style-based MIDI generator. Pick a genre, set your key, BPM, and complexity, and get back downloadable MIDI files for chords, bassline, melody, drums, and arpeggio — all harmonically aligned to the same chord progression.

## What it does

- Generates MIDI for five parts: **chords**, **bass**, **melody**, **drums**, and **arpeggio**
- Each part is generated from a style definition (JSON) that controls BPM range, chord progressions, extensions, rhythm density, swing, humanization, and more
- Melody is chord-aware — targets chord tones on downbeats and uses context-aware note durations (longer notes on structural arrivals)
- Bass and chords always share the same progression; arpeggio voices the same harmony above the chords
- Drums use genre-appropriate elements (kick patterns, ride, clap, crash, tom fills, swing) per style
- **Arrangement mode** — generates a full arrangement arc (intro → verse → chorus → outro) from a single bar count, with per-section complexity, dynamic scaling, and energy ramps at section transitions
- **Song Builder** — generates a complete song by stitching independently-produced sections using named templates (Verse–Chorus, V–C–Bridge, Extended, Compact, Minimal); each section type has distinct part layering, harmonic density, and dynamic profile
- **Style-aware playback** — in-browser preview uses genre-matched samplers and synthesis engines: acoustic kits, LinnDrum, breakbeats, Techno kit, Rhodes, clavinet, vibraphone, nylon guitar, accordion, strings, synth leads, and pads — routed automatically per style
- **Quality scorer** — every generation is scored across five musical dimensions (harmonic coherence, rhythm fit, register separation, density, mix balance) and returns a 0–1 score, label, and any issue flags alongside the MIDI
- **Generation library** — high-scoring generations are saved locally and used to influence rhythm patterns in future generations, improving style consistency over time
- In-browser MIDI preview with play/stop and mute per layer (drums / bass / melodic)
- Generation history — last 10 results stay accessible in the UI
- **Drag to DAW** — in the desktop app, drag any part directly into your DAW using the drag handle on each part card

### Mix quality features

- Per-part velocity scaling, stereo panning (CC10), reverb send (CC91), and expression (CC11)
- Style-specific reverb depths — cinematic/ambient styles get more room; tight electronic styles stay dry
- Chord voice balancing — bass note grounded, inner voices recede, soprano present
- Melody register ceiling — chord voicings are automatically capped below the melody's lowest note
- Sustain pedal (CC64) applied only to pad/hold styles; suppressed for staccato comping and orchestral brass/strings
- Phrase breath dynamics — 4-bar arc of subtle velocity swells across all melodic parts
- Arpeggio call-and-response — boosts arpeggio velocity during melody rests; reduces arpeggio complexity when melody is active
- Section energy ramps — gradual velocity fade-in over the first 8 beats of any energy-increasing transition (verse → chorus, intro → verse)
- Kick-sync chord comping — chord hits that land within an 8th-note of a kick drum receive a small velocity accent

---

## Styles

31 built-in styles across electronic, hip-hop, live/band, global, and mood categories:

`lofi` `boom_bap` `dark_trap` `drill` `grime` `trap_soul` `cloud_rap` `hyperpop`
`house` `techno` `drum_and_bass` `synthwave` `future_bass` `jersey_club`
`jazz` `latin_jazz` `bossa_nova` `soul` `rnb` `funk`
`afrobeats` `afropop` `samba` `cumbia` `reggaeton` `dancehall` `baile_funk`
`cinematic` `epic_orchestral` `ambient` `dark_ambient`

---

## Song Builder templates

| Template | Total bars | Structure |
|---|---|---|
| **Verse–Chorus** | 56 | Melodic intro · Verse×2 · Chorus×2 · Melodic outro |
| **V–C–Bridge** | 80 | No-drum intro · Verse×2 · Pre-chorus×2 · Chorus×2 · Bridge · Final chorus · Melodic outro |
| **Extended** | 80 | Foundation intro · Verse×2 · Chorus×2 · Instrumental · Bridge · Final chorus |
| **Compact** | 40 | Chords intro · Verse×2 · Chorus×2 · Chords outro |
| **Minimal** | 24 | Foundation intro · Main (16 bars) · Melodic outro |

Verse sections are 16 bars in all mainstream templates (Verse–Chorus, V–C–Bridge, Extended). Chorus sections are 8 bars.

---

## Stack

- **Backend** — Python, FastAPI, [mido](https://mido.readthedocs.io/)
- **Frontend** — Vue 3, TypeScript, Vite, [Tone.js](https://tonejs.github.io/), [@tonejs/midi](https://github.com/Tonejs/Midi)
- **Desktop** — Electron (Windows & Linux)

---

## Running in the browser

### Requirements

- Python 3.11+
- Node.js 18+

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

> **Important:** PyInstaller must be run on the same OS you are building for. To produce a Windows `.exe`, build on Windows. To produce a Linux `.deb` / AppImage, build on Linux.

### Build (Linux — one command)

```bash
./build.sh
```

`build.sh` handles everything: creates a Python venv if needed, installs dependencies, compiles the backend with PyInstaller, and packages the Electron app. On first run it will take a few minutes; subsequent runs are faster as the venv is reused.

**Output** — `frontend/release/GenreGrid-x.x.x.AppImage` and `frontend/release/genregrid_x.x.x_amd64.deb`

### Build (Windows — manual steps)

```powershell
# 1. Bundle the Python backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
pyinstaller genregrid.spec
deactivate

# 2. Build the Electron app
cd ..\frontend
npm install
npm run build:electron
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

### Drag to DAW

Each part card has a **⠿ drag handle**. Once a generation is ready, drag the handle directly into your DAW's track area to drop the `.mid` file. The handle dims briefly while the file is being prepared, then becomes fully opaque when ready to drag.

### User data

The desktop app stores exports and the generation library in:

- **Windows:** `%APPDATA%\genregrid-frontend\backend-data\`
- **Linux:** `~/.config/genregrid-frontend/backend-data/`

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
| `melody_scale` | string | Scale used for melody (can differ from harmony, e.g. pentatonic over diatonic chords) |
| `drums` | object | `hat_density`, `triplet_probability`, `snare_standard_beats`, `swing`, optional `kick_pattern`, `use_ride`, `use_clap`, `crash_on_bar_1`, `flam_prob`, `tom_fills` |
| `velocity_base` | int | Base MIDI velocity for chord notes |
| `vel_arc_start` | float | Velocity at bar 1 relative to peak (0.0–1.0); controls the dynamic build across the section |
| `groove_push` | float | Systematic timing offset in beats (negative = behind beat, positive = ahead) |
| `secondary_dominants` | bool | Allow secondary dominant substitutions in progressions |
| `tritone_substitution` | bool | Allow tritone substitutions on V chords |
| `chorus_key_shift` | int | Semitones to transpose the key for chorus sections in Song Builder |

To add style-aware **playback instruments**, update the mapping dicts in:
- `frontend/src/soundfonts/melodic.ts` — chords/melody/arpeggio instrument
- `frontend/src/soundfonts/bass.ts` — bass instrument
- `frontend/src/soundfonts/drums.ts` — drum kit
- `frontend/src/composables/useMidiPlayer.ts` — add to `SYNTH_STYLES`, `MELODIC_SYNTH_STYLES`, or `PAD_STYLES` if the style uses synthesis rather than samples

---

## Running tests

**Windows**
```powershell
cd backend
.venv\Scripts\activate
pytest
```

**Linux / macOS**
```bash
cd backend
source .venv/bin/activate
pytest
```
