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

## Styles

26 built-in styles across electronic, hip-hop, live/band, global, and mood categories:

`lofi` `boom_bap` `dark_trap` `cinematic` `house` `jazz` `drill` `afrobeats` `rnb` `reggaeton` `ambient` `techno` `drum_and_bass` `synthwave` `future_bass` `trap_soul` `cloud_rap` `jersey_club` `funk` `soul` `latin_jazz` `bossa_nova` `dancehall` `cumbia` `dark_ambient` `epic_orchestral`

## Stack

- **Backend** — Python, FastAPI, [mido](https://mido.readthedocs.io/)
- **Frontend** — Vue 3, TypeScript, Vite, [Tone.js](https://tonejs.github.io/), [@tonejs/midi](https://github.com/Tonejs/Midi)

## Setup

### Requirements

- Python 3.11+
- Node.js 18+

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
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

The UI runs at `http://localhost:5173`.

Run both in separate terminal tabs.

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

```bash
cd backend
source venv/bin/activate
pytest
```
