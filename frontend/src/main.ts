/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License as published by the Free Software
 * Foundation, either version 3 of the License, or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
 * <https://www.gnu.org/licenses/> for details.
 */
import { createApp } from 'vue'
import App from './App.vue'
import './styles/themes.css'
import './composables/useTheme'   // applies the persisted theme before first paint
import { installGlobalErrorHandlers, logError } from './composables/useErrorLog'
import * as Tone from 'tone'
import { getMasterCompressor, getMelodicBus, getDrumBus, getBassBus } from './soundfonts/loader'

// Use a larger audio buffer than Tone's low-latency default. The heavy synth graph
// underruns the small default buffer → brief audible glitches (on every platform); a bigger
// buffer trades a little latency (fine for a music player) for a stable, glitch-free render.
// latencyHint takes seconds here (the Web Audio API accepts a number; Tone's typing only
// lists the string presets, so we build the raw AudioContext and hand it to Tone).
Tone.setContext(new Tone.Context(new AudioContext({ latencyHint: 0.3 })))

// TEMP audio debug hook — probe the live graph from DevTools via window.__gg
;(window as unknown as { __gg: unknown }).__gg = {
  Tone,
  ctx: () => Tone.getContext().rawContext,
  destVol: () => Tone.getDestination().volume.value,
  masterComp: getMasterCompressor,
  melodicBus: getMelodicBus,
  drumBus: getDrumBus,
  bassBus: getBassBus,
  // Attach a meter to the master compressor; call meter().getValue() during playback
  meterMaster: () => {
    const m = new Tone.Meter()
    getMasterCompressor().connect(m)
    return m
  },
}

console.log(
  '%cGenreGrid%c\nStyle-based MIDI generator\n%cCreated by TW Dover',
  'color:#00c8ff;font-size:22px;font-weight:700;letter-spacing:0.05em',
  'color:#4a7080;font-size:12px',
  'color:#2a6070;font-size:11px',
)

// ── On-screen debug HUD ──────────────────────────────────────────────────────
// A fixed overlay that mirrors console output for diagnosing the packaged app without
// DevTools. Toggle it with Ctrl/Cmd+Shift+D (starts hidden). Also lists every dev shortcut.
;(() => {
  // Keep these in sync with the handlers in electron/main.ts.
  const SHORTCUTS: Array<[string, string]> = [
    ['Ctrl/Cmd + Shift + D', 'Toggle this debug HUD'],
    ['Ctrl/Cmd + R', 'Reload'],
    ['Ctrl/Cmd + Shift + R', 'Hard reload (ignore cache)'],
    ['F12 / Ctrl/Cmd + Shift + I', 'Toggle DevTools'],
    ['Ctrl/Cmd + = / -', 'Zoom in / out'],
    ['Ctrl/Cmd + 0', 'Reset zoom'],
    ['F11', 'Toggle fullscreen'],
    ['Ctrl/Cmd + M', 'Minimize'],
    ['Ctrl/Cmd + W / Q', 'Quit'],
  ]

  const hud = document.createElement('div')
  hud.style.cssText = [
    'position:fixed', 'left:6px', 'bottom:6px', 'z-index:99999',
    'width:460px', 'max-height:48vh', 'overflow:auto', 'display:none',
    'background:rgba(0,0,0,0.85)', 'color:#8fe', 'font:11px/1.35 monospace',
    'padding:6px 8px', 'border:1px solid #0af', 'border-radius:6px', 'white-space:pre-wrap',
  ].join(';')

  const head = document.createElement('div')
  head.style.cssText = 'color:#ffd24a;border-bottom:1px solid #333;padding-bottom:4px;margin-bottom:4px'
  head.textContent = 'GenreGrid debug HUD — shortcuts:\n' +
    SHORTCUTS.map(([c, d]) => `  ${c.padEnd(30)} ${d}`).join('\n') + '\n── console ──'
  const logBox = document.createElement('div')
  hud.appendChild(head); hud.appendChild(logBox)
  const add = () => document.body && document.body.appendChild(hud)
  if (document.body) add(); else window.addEventListener('DOMContentLoaded', add)

  const line = (kind: string, args: unknown[]) => {
    const el = document.createElement('div')
    el.textContent = `${kind} ${args.map(a => {
      try { return typeof a === 'string' ? a : JSON.stringify(a) } catch { return String(a) }
    }).join(' ')}`
    if (kind === 'ERR') el.style.color = '#f66'
    if (kind === 'WARN') el.style.color = '#fb4'
    logBox.appendChild(el)
    while (logBox.childNodes.length > 80) logBox.removeChild(logBox.firstChild!)
    if (hud.style.display !== 'none') hud.scrollTop = hud.scrollHeight
  }
  const orig = { log: console.log, warn: console.warn, error: console.error }
  console.log = (...a: unknown[]) => { orig.log(...a); line('LOG', a) }
  console.warn = (...a: unknown[]) => { orig.warn(...a); line('WARN', a) }
  console.error = (...a: unknown[]) => { orig.error(...a); line('ERR', a) }

  // Ctrl/Cmd+Shift+D toggles the HUD. Handled in the renderer (main.ts intentionally lets
  // this key fall through) so the overlay owns its own visibility.
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'd') {
      e.preventDefault()
      hud.style.display = hud.style.display === 'none' ? 'block' : 'none'
      if (hud.style.display === 'block') hud.scrollTop = hud.scrollHeight
    }
  }, true)

  console.log('[hud] Ready. Press Ctrl/Cmd+Shift+D to toggle this debug HUD.')
})()

// Catches anything that wasn't already wrapped in a try/catch — an
// unanticipated bug, not just the ones we knew to handle.
installGlobalErrorHandlers()

const app = createApp(App)
app.config.errorHandler = (err, _instance, info) => {
  logError(`Vue error (${info})`, err)
}
app.mount('#app')
