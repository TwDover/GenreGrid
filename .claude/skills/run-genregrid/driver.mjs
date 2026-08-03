/*
 * GenreGrid desktop runtime driver.
 *
 * Launches the real Electron shell (built, unpackaged) with a CDP debug port and
 * drives its renderer over the DevTools Protocol — no Playwright, no xvfb, no tmux.
 * Works on this headless-ish box because a real X DISPLAY (:0) is live; the same
 * script would need `xvfb-run` on a truly displayless host.
 *
 * Why CDP and not Playwright: playwright-core isn't installed here, and Electron's
 * remote-debugging endpoint is enough — see frontend/scripts/bench_render.mjs, which
 * drives plain Chromium the same way (Node built-in WebSocket/fetch, zero deps).
 *
 * Usage (run from anywhere; paths are resolved absolutely):
 *   node driver.mjs smoke                 # launch, wait ready, screenshot, print app state, quit
 *   node driver.mjs screenshot out.png    # launch, screenshot to out.png, quit
 *   node driver.mjs eval "<js expression>" # evaluate in the renderer, print JSON result, quit
 *   node driver.mjs run scenario.mjs      # launch, then run a scenario module (see bottom of file)
 *
 * Env:
 *   GG_PORT        CDP port (default 9444)
 *   GG_SHOT        default screenshot path for `smoke` (default <scratch>/gg-smoke.png)
 *   GG_NO_BACKEND  set to skip auto-starting the backend
 *
 * Copyright (C) 2026 Tw Dover. GPL-3.0-or-later; NO WARRANTY.
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SKILL_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(SKILL_DIR, '../../..');          // <repo>/.claude/skills/run-genregrid → <repo>
const FRONTEND = path.join(REPO, 'frontend');
const VENV_PY = path.join(REPO, '.venv', 'bin', 'python');
const ELECTRON = path.join(FRONTEND, 'node_modules', '.bin', 'electron');
const MAIN_JS = path.join(FRONTEND, 'dist-electron', 'main.js');
const PORT = Number(process.env.GG_PORT || 9444);
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ── build (only if the app hasn't been built) ────────────────────────────────
function ensureBuilt() {
  if (fs.existsSync(MAIN_JS) && fs.existsSync(path.join(FRONTEND, 'dist', 'index.html'))) return;
  console.error('[driver] building app (npx vite build --config vite.electron.config.ts)…');
  const r = spawnSync('npx', ['vite', 'build', '--config', 'vite.electron.config.ts'], {
    cwd: FRONTEND, stdio: 'inherit', env: process.env,
  });
  if (r.status !== 0) throw new Error('build failed');
}

// ── backend (Electron does NOT spawn it when unpackaged; the renderer needs :8000) ──
let backend = null;
async function ensureBackend() {
  if (process.env.GG_NO_BACKEND) return;
  const up = async () => {
    try { return (await fetch('http://localhost:8000/styles')).ok; } catch { return false; }
  };
  if (await up()) { console.error('[driver] backend already up on :8000'); return; }
  if (!fs.existsSync(VENV_PY)) { console.error('[driver] WARN: no .venv; start backend manually or the UI will show errors'); return; }
  console.error('[driver] starting backend (uvicorn app.main:app --port 8000)…');
  backend = spawn(VENV_PY, ['-m', 'uvicorn', 'app.main:app', '--port', '8000'], {
    cwd: path.join(REPO, 'backend'),
    env: { ...process.env, GENREGRID_DATA_DIR: path.join(REPO, 'backend', '.gg-driver-data') },
    stdio: 'ignore', detached: true,
  });
  for (let i = 0; i < 60 && !(await up()); i++) await sleep(500);
  console.error((await up()) ? '[driver] backend ready' : '[driver] WARN: backend did not come up');
}

// ── electron launch + CDP ────────────────────────────────────────────────────
let child = null;
function killTree() {
  if (child) { try { process.kill(-child.pid, 'SIGKILL'); } catch { /* */ } try { child.kill('SIGKILL'); } catch { /* */ } }
  if (backend) { try { process.kill(-backend.pid, 'SIGKILL'); } catch { /* */ } }
}
process.on('exit', killTree);
process.on('SIGINT', () => { killTree(); process.exit(130); });
process.on('SIGTERM', () => { killTree(); process.exit(143); });

function launchElectron() {
  const env = { ...process.env, DISPLAY: process.env.DISPLAY || ':0', NODE_ENV: 'production' };
  delete env.ELECTRON_RUN_AS_NODE;   // this env sets it → Electron would run as plain Node and crash
  const args = ['.', `--remote-debugging-port=${PORT}`, '--no-sandbox', '--disable-http-cache'];
  // GG_FAKE_MEDIA=1 — synthesize a non-silent getUserMedia signal and auto-grant its
  // permission prompt, for scenarios exercising mic capture (roadmap 9.4) with no real
  // microphone on this host. Opt-in: every other scenario keeps the default (no mic).
  if (process.env.GG_FAKE_MEDIA) args.push('--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream');
  child = spawn(ELECTRON, args, {
    cwd: FRONTEND, env, stdio: ['ignore', 'pipe', 'pipe'], detached: true,   // own group so we can kill the real electron, not just the .bin shim
  });
  let log = '';
  child.stdout.on('data', d => { log += d; });
  child.stderr.on('data', d => { log += d; });
  child.on('exit', c => { if (c && !shuttingDown) console.error('[driver] electron exited early, code', c, '\n', log.slice(-2000)); });
  return () => log;
}
let shuttingDown = false;

async function cdpPage() {
  for (let i = 0; i < 150; i++) {
    try {
      const targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
      const page = targets.find(t => t.type === 'page' && t.url?.startsWith('http') && t.webSocketDebuggerUrl);
      if (page) return page;
    } catch { /* not up yet */ }
    await sleep(200);
  }
  throw new Error('CDP page target never appeared');
}

let msgId = 0;
function rpc(ws, method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++msgId;
    const onMsg = ev => {
      const m = JSON.parse(ev.data);
      if (m.id === id) { ws.removeEventListener('message', onMsg); m.error ? reject(new Error(method + ': ' + m.error.message)) : resolve(m.result); }
    };
    ws.addEventListener('message', onMsg);
    ws.send(JSON.stringify({ id, method, params }));
  });
}

// The API handed to scenarios and used by the built-in subcommands.
function makeApi(ws) {
  const api = {
    raw: (method, params) => rpc(ws, method, params),
    async evaluate(expr) {
      const r = await rpc(ws, 'Runtime.evaluate', { expression: `(async()=>{${expr}})()`, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error('eval threw: ' + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
      return r.result.value;
    },
    async screenshot(file) {
      const shot = await rpc(ws, 'Page.captureScreenshot', { format: 'png' });
      fs.writeFileSync(file, Buffer.from(shot.data, 'base64'));
      return file;
    },
    async waitReady(timeoutMs = 30000) {
      const t0 = Date.now();
      while (Date.now() - t0 < timeoutMs) {
        const ok = await api.evaluate(`return !!document.querySelector('#app') && document.querySelector('#app').children.length > 0;`);
        if (ok) return true;
        await sleep(200);
      }
      throw new Error('app never mounted');
    },
    sleep,
  };
  return api;
}

async function connect() {
  const getLog = launchElectron();
  try {
    const page = await cdpPage();
    const ws = new WebSocket(page.webSocketDebuggerUrl);
    await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej); });
    await rpc(ws, 'Runtime.enable');
    await rpc(ws, 'Page.enable');
    const api = makeApi(ws);
    await api.waitReady();
    return { ws, api };
  } catch (e) {
    throw new Error(e.message + '\n--- electron log ---\n' + getLog().slice(-2000));
  }
}

// ── main ─────────────────────────────────────────────────────────────────────
const [cmd, arg] = process.argv.slice(2);
const SCRATCH = process.env.GG_SHOT || path.join(process.env.TMPDIR || '/tmp', 'gg-smoke.png');

try {
  ensureBuilt();
  await ensureBackend();
  const { api } = await connect();

  if (cmd === 'smoke' || !cmd) {
    const state = await api.evaluate(`return {
      title: document.title,
      styleSelectorPresent: !!document.querySelector('select, [class*=style]'),
      transportPresent: !!document.querySelector('[class*=transport], .tb, footer'),
      bodyText: (document.body.innerText || '').slice(0, 200),
    };`);
    const file = await api.screenshot(SCRATCH);
    console.log('APP STATE', JSON.stringify(state, null, 2));
    console.log('SCREENSHOT', file);
  } else if (cmd === 'screenshot') {
    const file = await api.screenshot(path.resolve(arg || SCRATCH));
    console.log('SCREENSHOT', file);
  } else if (cmd === 'eval') {
    if (!arg) throw new Error('usage: node driver.mjs eval "<expression>"');
    console.log('RESULT', JSON.stringify(await api.evaluate(arg)));
  } else if (cmd === 'run') {
    if (!arg) throw new Error('usage: node driver.mjs run <scenario.mjs>');
    const mod = await import(path.resolve(arg));
    await mod.default(api);
  } else {
    throw new Error(`unknown command: ${cmd}`);
  }
  shuttingDown = true;
  process.exit(0);
} catch (e) {
  shuttingDown = true;
  console.error('DRIVER ERROR:', e.message);
  process.exit(1);
}

/*
 * Scenario module shape (for `node driver.mjs run scenario.mjs`):
 *
 *   export default async function (gg) {
 *     await gg.evaluate(`window.someAppHook.doThing()`);
 *     await gg.screenshot('/tmp/after.png');
 *   }
 *
 * `gg` = { evaluate, screenshot, waitReady, raw(method,params), sleep }.
 * To reach the app's own composables, temporarily expose them on the existing
 * `window.__gg` debug hook in frontend/src/main.ts, rebuild, then evaluate against
 * them — see the custom-instruments desktop pass in docs/custom-instruments-design.md.
 */
