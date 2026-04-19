# GenreGrid

A style-based MIDI generator. Pick a genre, set your key, BPM, and complexity, and get back downloadable MIDI files for chords, bassline, melody, and drums — all harmonically aligned to the same chord progression.

## What it does

- Generates MIDI for four parts: **chords**, **bass**, **melody**, and **drums**
- Each part is generated from a style definition (JSON) that controls BPM range, chord progressions, extensions, rhythm density, swing, and more
- Melody is chord-aware — it targets chord tones on downbeats
- Bass and chords always share the same progression
- Drums use genre-appropriate elements (ride, clap, crash, tom fills) per style
- In-browser MIDI preview with play/stop per part
- Generation history — last 10 results stay accessible in the UI
- **Generation library** — high-scoring generations are saved locally and used to influence rhythm patterns in future generations, improving style consistency over time
- **Quality scorer** — every generation is scored across five musical dimensions (harmonic coherence, rhythm fit, register separation, density, mix balance) and returns a 0–1 score, label, and any issue flags alongside the MIDI
- **Drag to DAW** — in the desktop app, drag any part directly into your DAW (Ableton, FL Studio, Reason, etc.) using the drag handle on each part card

## Styles

26 built-in styles across electronic, hip-hop, live/band, global, and mood categories:

`lofi` `boom_bap` `dark_trap` `cinematic` `house` `jazz` `drill` `afrobeats` `rnb` `reggaeton` `ambient` `techno` `drum_and_bass` `synthwave` `future_bass` `trap_soul` `cloud_rap` `jersey_club` `funk` `soul` `latin_jazz` `bossa_nova` `dancehall` `cumbia` `dark_ambient` `epic_orchestral`

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

| Field | Description |
|---|---|
| `bpm_range` | `[min, max]` suggested tempo |
| `default_scale` | `major` or `minor` (and any mode in `constants.py`) |
| `preferred_keys` | List of root notes |
| `progression_templates` | List of roman numeral progressions to pick from |
| `chord_extensions` | Probabilities for 7th and 9th chords |
| `bass` | `pattern_density`, `octave_jumps`, `sustain_bias` |
| `melody` | `density`, `stepwise_motion`, `leap_probability`, `rest_probability`, `range` |
| `drums` | `hat_density`, `triplet_probability`, `snare_standard_beats`, `swing`, optional `use_ride`, `use_clap`, `crash_on_bar_1`, `tom_fills` |

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
