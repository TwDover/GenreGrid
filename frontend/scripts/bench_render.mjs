/*
 * GenreGrid — WAV-export render benchmark.
 *
 * Measures how long an OfflineAudioContext takes to render a full song's worth
 * of synth-only audio — the real cost behind the "1-2 min" WAV export wait (song
 * *generation* is ~0.5s; see docs/roadmap.md). Runs in headless Chromium driven
 * over CDP, so it needs no X display and no Playwright JS package — only the
 * cached Chromium binary (Playwright's, or set CHROME_BIN) and Node >= 20.
 *
 * Usage:  node scripts/bench_render.mjs
 * Output: RESULT {"withVerbMs":..,"noVerbMs":..,"notes":..,"songSeconds":..}
 *
 * The graph mirrors offlineRender()'s: per-note oscillator+gain voices through a
 * convolution reverb + chorus + feedback delay + waveshaper limiter. Rendering
 * with FX vs. without isolates the reverb's share (measured ~8%): the dominant
 * cost is the per-note voice synthesis, so the optimization lever is timeline
 * parallelism (chunked Web Worker renders), not caching the reverb IR.
 *
 * Copyright (C) 2026 Tw Dover. GPL-3.0-or-later; NO WARRANTY.
 * See <https://www.gnu.org/licenses/>.
 */
import { spawn } from 'node:child_process';
import { globSync } from 'node:fs';
import os from 'node:os';

function findChrome() {
  if (process.env.CHROME_BIN) return process.env.CHROME_BIN;
  const patterns = [
    `${os.homedir()}/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell`,
    `${os.homedir()}/.cache/ms-playwright/chromium-*/chrome-linux64/chrome`,
  ];
  for (const p of patterns) {
    const hits = globSync(p).sort();
    if (hits.length) return hits[hits.length - 1];
  }
  throw new Error('No Chromium found. Set CHROME_BIN or install Playwright browsers.');
}

const PORT = 9333;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const chrome = spawn(findChrome(), [
  '--headless', '--disable-gpu', '--no-sandbox', '--mute-audio',
  `--remote-debugging-port=${PORT}`, 'about:blank',
], { stdio: ['ignore', 'ignore', 'ignore'] });

async function getWsUrl() {
  for (let i = 0; i < 100; i++) {
    try {
      const targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
      const page = targets.find(t => t.type === 'page' && t.webSocketDebuggerUrl);
      if (page) return page.webSocketDebuggerUrl;
    } catch { /* not up yet */ }
    await sleep(100);
  }
  throw new Error('CDP endpoint never came up');
}

const RENDER_EXPR = `(async () => {
  const BPM = 120, BARS = 56, SR = 44100;
  const seconds = BARS * 4 * 60 / BPM;   // 56 bars @120 = 112s of audio
  const total = seconds + 2.5;           // pad tail

  function buildNotes() {
    const notes = [];
    const push = (t, dur, freq, vel) => notes.push({ t, dur, freq, vel });
    for (let b = 0; b < BARS * 4; b++) {
      const bt = b * 60 / BPM;
      push(bt, 0.45, 55 * Math.pow(2, (b % 5) / 12), 0.9);                              // bass
      if (b % 2 === 0) for (const iv of [0, 4, 7]) push(bt, 0.9, 220 * Math.pow(2, iv / 12), 0.5); // chords
      for (let s = 0; s < 2; s++) push(bt + s * 0.5, 0.4, 440 * Math.pow(2, ((b + s) % 8) / 12), 0.7); // melody
      for (let s = 0; s < 4; s++) push(bt + s * 0.25, 0.2, 660 * Math.pow(2, (s % 4) / 12), 0.5);      // arp
      if (b % 4 === 0) for (const iv of [0, 7]) push(bt, 3.5, 330 * Math.pow(2, iv / 12), 0.35);       // pads
      if (b % 2 === 1) push(bt, 0.5, 550 * Math.pow(2, (b % 6) / 12), 0.5);              // counter-melody
      push(bt, 0.12, 60, 1.0); push(bt + 0.5, 0.05, 8000, 0.4);                         // drums
    }
    return notes;
  }
  function makeIR(ctx, decay) {
    const len = Math.floor(SR * decay), ir = ctx.createBuffer(2, len, SR);
    for (let ch = 0; ch < 2; ch++) {
      const d = ir.getChannelData(ch);
      for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2.5);
    }
    return ir;
  }
  async function render(withVerb) {
    const ctx = new OfflineAudioContext(2, Math.ceil(total * SR), SR);
    const master = ctx.createGain(); master.gain.value = 0.8;
    const ws = ctx.createWaveShaper(), curve = new Float32Array(1024);
    for (let i = 0; i < 1024; i++) { const x = (i / 512) - 1; curve[i] = Math.tanh(x * 1.2); }
    ws.curve = curve; master.connect(ws).connect(ctx.destination);
    const dry = ctx.createGain(); dry.connect(master);
    let busIn = dry;
    if (withVerb) {
      const pre = ctx.createGain(); pre.connect(dry);
      const chorusDelay = ctx.createDelay(); chorusDelay.delayTime.value = 0.025;
      const lfo = ctx.createOscillator(); lfo.frequency.value = 1.5;
      const lfoGain = ctx.createGain(); lfoGain.gain.value = 0.008;
      lfo.connect(lfoGain).connect(chorusDelay.delayTime); lfo.start(0);
      pre.connect(chorusDelay); chorusDelay.connect(master);
      const fbDelay = ctx.createDelay(); fbDelay.delayTime.value = 0.375;
      const fb = ctx.createGain(); fb.gain.value = 0.3;
      fbDelay.connect(fb).connect(fbDelay); pre.connect(fbDelay); fbDelay.connect(master);
      const conv = ctx.createConvolver(); conv.buffer = makeIR(ctx, 2.5);
      const wet = ctx.createGain(); wet.gain.value = 0.3;
      pre.connect(conv).connect(wet).connect(master);
      busIn = pre;
    }
    const notes = buildNotes();
    for (const n of notes) {
      const o = ctx.createOscillator();
      o.type = n.freq > 3000 ? 'square' : 'sawtooth'; o.frequency.value = n.freq;
      const g = ctx.createGain();
      g.gain.setValueAtTime(0, n.t);
      g.gain.linearRampToValueAtTime(n.vel * 0.25, n.t + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, n.t + n.dur);
      o.connect(g).connect(busIn); o.start(n.t); o.stop(n.t + n.dur + 0.02);
    }
    const t0 = performance.now();
    await ctx.startRendering();
    return { ms: Math.round(performance.now() - t0), notes: notes.length };
  }
  const a = await render(true), b = await render(false);
  return { withVerbMs: a.ms, noVerbMs: b.ms, notes: a.notes, songSeconds: Math.round(seconds) };
})()`;

let msgId = 0;
function send(ws, method, params) {
  return new Promise((resolve, reject) => {
    const id = ++msgId;
    const onMsg = ev => {
      const m = JSON.parse(ev.data);
      if (m.id === id) { ws.removeEventListener('message', onMsg); m.error ? reject(new Error(m.error.message)) : resolve(m.result); }
    };
    ws.addEventListener('message', onMsg);
    ws.send(JSON.stringify({ id, method, params }));
  });
}

try {
  const ws = new WebSocket(await getWsUrl());
  await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej); });
  await send(ws, 'Runtime.enable', {});
  const r = await send(ws, 'Runtime.evaluate', { expression: RENDER_EXPR, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails));
  console.log('RESULT', JSON.stringify(r.result.value));
  ws.close();
} catch (e) {
  console.log('ERROR', e.message);
  process.exitCode = 1;
} finally {
  chrome.kill('SIGKILL');
}
