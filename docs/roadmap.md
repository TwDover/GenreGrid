# GenreGrid Roadmap

A living, prioritized roadmap from the July 2026 project survey. Check items off as
they land; add new findings under the right phase so nothing gets lost.

**Status legend:** `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` won't do / obsolete

_Last updated: 2026-07-23 — Phase 1 complete (see Done log)._

---

## Health snapshot (at survey time)

- Backend: ~14.3k LoC Python, **132 tests passing**, ruff gate (E/F/W) configured.
- Frontend: ~11.3k LoC TS/Vue, **12 tests** (3 files) — thin coverage.
- Electron: `contextIsolation: true`, `nodeIntegration: false` — securely configured.
- Overall: a well-built project. Items below are refinements, not firefighting.

---

## Phase 1 — Harden (high value, low risk)

- [x] **Path traversal in `download_export`** — hardened all three export routes with a
  containment check (`_safe_export_dir` + `is_relative_to`) and a strict id pattern; new
  regression test. → `backend/app/api/routes_generate.py`
- [x] **CORS `*` in the packaged app** — replaced with a localhost/127.0.0.1 origin regex
  (covers the renderer's random port, blocks external sites at preflight). Electron no
  longer sets `CORS_ORIGINS: '*'`. → `backend/app/main.py`, `frontend/electron/main.ts`
  - [ ] _Optional follow-up:_ per-session token as defense-in-depth on mutating JSON
    endpoints. Deferred — a header token complicates file-URL/audio loading; the origin
    allowlist already closes the browser-based attack.
- [x] **`will-navigate` / `setWindowOpenHandler` guards** added — in-app navigation is
  same-origin only; external links open in the OS browser. → `frontend/electron/main.ts`
- [x] **`save-temp-file` IPC** now `path.basename()`s the renderer-supplied filename.
  → `frontend/electron/main.ts`
- [x] **`create_custom_style`** now validates via `CustomStyleRequest` (typed core fields
  + bounds, `extra="allow"` for rich style config). → `backend/app/models/schemas.py`
- [x] **Bundle the Salamander piano samples locally** — the 30-file sample set now lives
  in `frontend/public/samples/piano/` (2 MB) and `loader.ts` loads `/samples/piano/`, so
  the flagship piano works fully offline and no longer fetches from `tonejs.github.io`.
  Attribution (CC-BY 3.0, Alexander Holm) added to `DATA_LICENSES.md`.
  → `frontend/src/soundfonts/loader.ts`

## Phase 2 — Sound polish

- [ ] **Master bus glue/limiting** — master is a unity `Gain` (a `DynamicsCompressor`
  renders silence on Linux Electron), so a full arrangement can peak/clip with nothing
  catching it. Add a Linux-safe JS soft-clip / look-ahead limiter.
  → `frontend/src/soundfonts/loader.ts:39`
- [ ] **Velocity layers / round-robins in sample sets** — ~4 MB total, ~one mp3 per
  note-zone; wide pitch-shifting sounds synthetic. More velocity layers = fastest
  realism gain. → `frontend/public/samples/`
- [ ] **Loudness normalization across styles** — target an LUFS level per style so
  perceived volume doesn't jump between styles.
- [ ] **Per-style FX presets** — reverb/chorus/delay are currently shared and fixed.
  → `frontend/src/soundfonts/loader.ts` (buses)

## Phase 3 — Performance & refactor

- [ ] **Parallelize full-song section generation** — song builds take ~1–2 min and
  sections generate serially though they're embarrassingly parallel. SSE progress
  plumbing (`generate-stream`) already exists.
  → `backend/app/api/routes_song.py`
- [ ] **Extract song/arrangement logic out of route god-files into `services/`** —
  handlers should be thin. → `routes_song.py` (1498), `routes_generate.py` (1299)
- [ ] **Split `useMidiPlayer.ts`** (1018 lines) into focused composables.
- [ ] **Log swallowed exceptions** — 27 broad/bare `except`; several return silently
  (e.g. `record_export_keep`). Add logging.
- [ ] **Grow frontend test coverage** — 12 tests vs 132 backend; the audio scheduler and
  WAV-render path (most fragile code) are untested.
- [ ] **Clear deprecation warnings** — Starlette `TestClient` httpx warning; Electron
  numeric-level `console-message` signature. → `frontend/electron/main.ts:206`

## Phase 4 — Features

- [ ] **Expose the data-driven priors toggle in the UI** — wired end-to-end already, no
  frontend control yet. Low effort.
- [ ] **Non-4/4 time signatures** (6/8, 3/4, 7/8) — currently hardcoded `numerator=4`.
  → `backend/app/services/midi_writer.py:162`
- [ ] **Custom soundfont / SF2 upload** + per-part instrument picker.
- [ ] **Surface WAV/offline-audio export more prominently** — already implemented
  (OfflineAudioContext + render queue); just under-discovered.
- [ ] **Tempo automation & mid-song modulation** — partial today (`chorus_key_shift`).

---

## Done log

- **2026-07-23 — Phase 1 security hardening** (uncommitted working changes):
  - Export downloads hardened against path traversal (`_safe_export_dir` containment
    check on `/exports/{gen_id}/bundle.zip`, `/sections.zip`, and `/{filename}`).
  - CORS locked to a localhost-only origin regex; dropped the packaged `CORS_ORIGINS=*`.
  - Electron `will-navigate` + `setWindowOpenHandler` guards; `save-temp-file` basenames
    the filename.
  - `POST /styles/custom` validated with a `CustomStyleRequest` model.
  - Salamander piano bundled locally (`public/samples/piano/`, 2 MB) — flagship piano is
    now fully offline; CC-BY 3.0 attribution added to `DATA_LICENSES.md`.
  - Tests: +3 (traversal rejection, CORS allow/deny). Suite 131→134 green; ruff clean;
    frontend `vue-tsc` + vitest clean.

**Phase 1 complete.** Next up: Phase 2 (sound polish) — master limiter is the natural
first step and pairs well with the now-local piano.
