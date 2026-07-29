---
name: run-genregrid
description: Launch, run, screenshot, or drive the GenreGrid desktop app (Electron + FastAPI MIDI generator). Use to start the app, take a screenshot, poke the UI, or verify a change works in the real Electron shell (not just tests) — including audio/IPC behavior that only the desktop runtime exposes.
---

# Running GenreGrid

GenreGrid is an **Electron** desktop app (Vue 3 renderer) that spawns a **FastAPI**
backend. Its interesting behavior — Web Audio playback, WAV export, and the
custom-instrument IPC/blob-URL path — only exists in the running Electron shell, so the
deliverable here is a driver, not a "npm start opens a window" note.

**The driver** — [`.claude/skills/run-genregrid/driver.mjs`](driver.mjs) — launches the
built, unpackaged app with a CDP debug port and drives its renderer over the DevTools
Protocol. **No Playwright, no xvfb, no tmux** (this host has a live `DISPLAY=:0` and the
`electron` binary; the same script needs `xvfb-run` only on a truly displayless box). It
auto-builds if needed and auto-starts the backend. Paths below are relative to the repo root.

> All commands were run from the repo root on Linux with Node 22. Electron's runtime
> shared libs were already present on this host; a bare container also needs the usual
> Chromium libs (`libnss3 libgbm1 libasound2t64 libgtk-3-0 libxss1 libxkbcommon0
> libatk-bridge2.0-0 libcups2 libdrm2`) — not verified here since they were installed.

## Prerequisites (one-time)

```bash
# Node deps for the Electron app + Python venv for the backend (both already present here):
cd frontend && npm install && cd ..
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
```

## Build

The driver runs the **built** app (`frontend/dist/` + `frontend/dist-electron/`), not live
source — there's no HMR in this path. Build once (the driver also does this automatically
if the output is missing):

```bash
cd frontend && npx vite build --config vite.electron.config.ts && cd ..
```

Re-run this after any change to renderer/electron source, or the driver runs the old code.

## Run (agent path — use this)

The driver launches Electron, waits for the Vue app to mount, does one thing, and tears
down cleanly (it kills the whole process group — see Gotchas). One launch per invocation
(~4s startup); that's fine for the Bash-tool workflow.

```bash
# Launch, screenshot the window, and print app state. Screenshot → $GG_SHOT (default /tmp/gg-smoke.png).
GG_SHOT=/tmp/gg.png node .claude/skills/run-genregrid/driver.mjs smoke

# Just a screenshot to an explicit path:
node .claude/skills/run-genregrid/driver.mjs screenshot /tmp/gg.png

# Evaluate any JS in the renderer and print the JSON result:
node .claude/skills/run-genregrid/driver.mjs eval "return document.title;"
node .claude/skills/run-genregrid/driver.mjs eval "const r = await fetch('http://localhost:8000/styles').then(r=>r.json()); return (r.styles||r).length;"

# Run a multi-step scenario module (clicks, waits, screenshots) in one launch:
GG_SHOT=/tmp/setup.png node .claude/skills/run-genregrid/driver.mjs run .claude/skills/run-genregrid/scenarios/open-setup.mjs
```

**Always look at the screenshot** — a blank/error frame means it didn't really load.

### Writing a scenario

A scenario is an ES module with a default async function that receives the driver API.
See [`scenarios/open-setup.mjs`](scenarios/open-setup.mjs) for a working example (clicks
"Open Setup", asserts the drawer, screenshots).

```js
export default async function (gg) {
  await gg.evaluate(`[...document.querySelectorAll('button')].find(b => b.textContent.includes('Open Setup'))?.click()`);
  await gg.sleep(600);
  await gg.screenshot('/tmp/after.png');
}
// gg = { evaluate(expr), screenshot(file), waitReady(ms), raw(method,params), sleep(ms) }
// Clicks go through evaluate(querySelector().click()), NOT a coordinate system.
```

### Reaching the app's own code (composables/store/engine)

`evaluate` runs in the page's main world. App internals aren't global, so to drive a
composable directly, **temporarily** extend the existing `window.__gg` debug hook in
[`frontend/src/main.ts`](../../../frontend/src/main.ts) (it already exposes Tone/buses),
**rebuild**, evaluate against it, then revert. This is exactly how the custom-instruments
desktop pass was driven — see [`docs/custom-instruments-design.md`](../../../docs/custom-instruments-design.md)
(that pass found and fixed a real "An object could not be cloned" IPC bug and left a
`useCustomInstruments.test.ts` regression guard).

## Run (human path)

`cd frontend && npm run dev:electron` opens a real window with HMR — useless headless, and
it expects you to run the backend yourself (`dev.sh` does both). Prefer the driver.

## Test

```bash
cd frontend && npx vitest run          # 124 frontend tests
cd backend && ../.venv/bin/python -m pytest -q   # backend suite
```

## Gotchas (battle scars — all hit this session)

- **`ELECTRON_RUN_AS_NODE=1` may be in the environment.** It makes the `electron` binary
  run as plain Node, which dies on `import { nativeImage } from 'electron'`. The driver
  deletes it from the child env; if you launch Electron yourself, do the same.
- **The `node_modules/.bin/electron` shim orphans the real `dist/electron` child** when
  killed (e.g. by an outer `timeout`). Orphans keep the debug port and **serve a stale
  bundle to the next run**, so a rebuild appears to "not take." The driver spawns
  `detached` and kills the process group (`process.kill(-pid)`); if you see stale
  behavior, `pkill -9 -f node_modules/electron/dist/electron`.
- **Unpackaged Electron does NOT spawn the backend** (only `app.isPackaged` does). The
  renderer expects it on `http://localhost:8000`; the driver auto-starts `uvicorn` if
  it's not already up. Without a backend the UI loads but generation/styles error.
- **Renderer is served over local http, not `app://`.** On Linux the `app://` origin
  renders Web Audio **silent** (documented in `frontend/electron/main.ts`), so the built
  app uses an http static server — the driver relies on that being the packaged path too.
- **`--disable-http-cache`** is passed, else Electron may serve a cached old JS bundle
  after a rebuild.
- **userData lives at `~/.config/genregrid-frontend/`** (Electron uses package `name`
  when unpackaged). Custom instruments, caches, and localStorage persist there between
  runs — clear `instruments/` + `Cache`/`Code Cache`/`GPUCache` for a clean baseline.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `does not provide an export named 'nativeImage'` (Node stack, no Electron frames) | `ELECTRON_RUN_AS_NODE` is set — unset it. |
| `CDP page target never appeared` and/or a rebuild seems ignored | Stray Electron from a prior run holds the port. `pkill -9 -f node_modules/electron/dist/electron`. |
| UI loads but styles/generation error | Backend not on `:8000`. `GG_NO_BACKEND` unset lets the driver start it; else run `.venv/bin/python -m uvicorn app.main:app --port 8000` from `backend/`. |
| Blank/error screenshot | App didn't mount — check the electron log the driver prints on failure. |
