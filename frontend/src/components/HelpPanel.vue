<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<!--
  First-run orientation. The rest of the app documents itself at the control
  level (hints, tooltips); this panel gives the one thing those can't — the
  mental model: what a style is, the three modes, and the overall workflow.
-->
<template>
  <div class="help-overlay" @click.self="emit('close')">
    <div class="help-modal" role="dialog" aria-modal="true" aria-label="How GenreGrid works">
      <div class="help-header">
        <span class="help-title">How GenreGrid works</span>
        <button class="btn btn-quiet btn-icon" @click="emit('close')" title="Close">✕</button>
      </div>

      <div class="help-body">
        <p class="help-lead">
          GenreGrid writes MIDI for you — chords, bass, melody, drums and more —
          in the feel of a chosen <strong>style</strong>. Everything it makes is
          real MIDI you audition here and drag into your DAW.
        </p>

        <section class="help-sec">
          <span class="eyebrow">1 · Pick a style</span>
          <p>
            A <strong>style</strong> is a genre recipe — its typical tempo, scale,
            chord moves and groove (dark trap, lo-fi, house…). It seeds every part.
            Browse or edit styles from <em>Setup</em>, or blend two together under
            <em>Advanced</em>.
          </p>
        </section>

        <section class="help-sec">
          <span class="eyebrow">2 · Choose what to make</span>
          <ul class="help-modes">
            <li><strong>Loop</strong> — one repeating section; every part plays across every bar. Great for a quick idea or a drag-in loop.</li>
            <li><strong>Arrangement</strong> — one bar count auto-shaped into a full arc: intro · verse · chorus · outro.</li>
            <li><strong>Full Song</strong> — a complete, sectioned song from a template (or your own section list), with key lifts and dynamics.</li>
          </ul>
        </section>

        <section class="help-sec">
          <span class="eyebrow">3 · Shape the feel</span>
          <p>
            <strong>Complexity</strong> adds notes and motion; <strong>Variation</strong>
            keeps repeats from being identical; <strong>Feel</strong> (humanize) loosens
            timing and velocity from robotic to raw. Leave <em>Seed</em> blank for a fresh
            result each time, or set it to reproduce one exactly.
          </p>
        </section>

        <section class="help-sec">
          <span class="eyebrow">4 · Audition &amp; export</span>
          <p>
            Results land in the workspace. Play them from the transport bar, regenerate
            a single part you don't like, then <strong>drag any stem straight into your
            DAW</strong> — or export MIDI, a WAV, or stems. The <strong>Quality</strong>
            readout scores each result across musical dimensions and flags likely
            issues; hover any bar or flag for what it means.
          </p>
        </section>

        <p class="help-foot">
          Open this any time with <kbd>?</kbd>. The <kbd>⌨</kbd> button in the top
          bar lists keyboard shortcuts.
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const emit = defineEmits<{ (e: 'close'): void }>()
</script>

<style scoped>
.help-overlay {
  position: fixed; inset: 0; z-index: 60;
  background: color-mix(in srgb, var(--sunken) 70%, transparent);
  backdrop-filter: blur(3px);
  display: flex; align-items: center; justify-content: center;
  padding: var(--s4);
}
.help-modal {
  background: var(--raised);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-lift);
  width: min(560px, 100%);
  max-height: calc(100vh - 2 * var(--s4));
  display: flex; flex-direction: column;
}
.help-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--s4) var(--s5);
  border-bottom: 1px solid var(--line);
}
.help-title { font-size: var(--t-title); font-weight: 620; letter-spacing: -.01em; }

.help-body {
  padding: var(--s4) var(--s5) var(--s5);
  overflow-y: auto;
  display: flex; flex-direction: column; gap: var(--s4);
}
.help-lead { font-size: var(--t-body); color: var(--ink); line-height: 1.55; margin: 0; }
.help-lead strong { color: var(--accent); font-weight: 600; }

.help-sec { display: flex; flex-direction: column; gap: var(--s2); }
.help-sec p { margin: 0; font-size: var(--t-meta); color: var(--ink-dim); line-height: 1.55; }
.help-sec strong { color: var(--ink); font-weight: 600; }
.help-sec em { color: var(--ink-dim); font-style: normal; text-decoration: underline; text-decoration-color: var(--line); text-underline-offset: 2px; }

.help-modes { margin: 0; padding-left: var(--s4); display: flex; flex-direction: column; gap: var(--s2); }
.help-modes li { font-size: var(--t-meta); color: var(--ink-dim); line-height: 1.5; }
.help-modes strong { color: var(--ink); font-weight: 600; }

.help-foot {
  margin: 0; padding-top: var(--s3);
  border-top: 1px solid var(--line);
  font-size: var(--t-meta); color: var(--ink-faint);
}
kbd {
  font-family: var(--f-mono); font-size: var(--t-micro);
  color: var(--accent); background: var(--sunken);
  border: 1px solid var(--line); border-radius: var(--r-sm);
  padding: 0.1rem 0.4rem;
}
</style>
