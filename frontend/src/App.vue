<!--
  GenreGrid — a style-based MIDI generator.
  Copyright (C) 2026 Tw Dover

  This program is free software: you can redistribute it and/or modify it under
  the terms of the GNU General Public License v3 or (at your option) any later
  version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
-->
<template>
  <HomePage />
</template>

<script setup lang="ts">
import HomePage from './pages/HomePage.vue'
</script>

<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body { height: 100%; }

body {
  font-family: var(--f-ui);
  font-size: var(--t-body);
  line-height: 1.5;
  background: var(--ground);
  color: var(--ink);
  overflow: hidden;
  -webkit-font-smoothing: antialiased;
}

:where(button, a, input, select, summary, [tabindex]):focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: var(--r-sm);
}

/* ── Shared type helpers ──────────────────────────────────────────────────── */
.mono { font-family: var(--f-mono); font-variant-numeric: tabular-nums; }
.eyebrow {
  font-size: var(--t-micro);
  text-transform: uppercase;
  letter-spacing: 0.09em;
  font-weight: 600;
  color: var(--ink-faint);
}

/* ═══════════════════════════════════════════════════════════════════════════
   BUTTONS — three kinds, app-wide. primary (one per context) / default / quiet.
   `.btn-primary` and `.btn-quiet` are self-sufficient so legacy markup that
   uses them without `.btn` keeps working.
   ═══════════════════════════════════════════════════════════════════════════ */
.btn {
  font: inherit;
  font-size: var(--t-body);
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--s2);
  height: 34px;
  padding: 0 var(--s3);
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: var(--raised);
  color: var(--ink);
  cursor: pointer;
  white-space: nowrap;
  user-select: none;
  transition: background .14s, border-color .14s, color .14s, filter .14s;
}
.btn:hover:not(:disabled) { border-color: var(--ink-faint); }
.btn:disabled { opacity: .45; cursor: not-allowed; }
.btn-icon { width: 34px; padding: 0; }

/* Compact variant for dense chrome (history rows, per-part toolbars). */
.btn-sm { height: 28px; padding: 0 var(--s2); font-size: var(--t-meta); gap: var(--s1); }
.btn-sm.btn-icon { width: 28px; padding: 0; }

.btn-primary {
  font: inherit;
  font-size: var(--t-body);
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--s2);
  height: 34px;
  padding: 0 var(--s3);
  border-radius: var(--r-sm);
  border: 1px solid var(--accent);
  background: var(--accent);
  color: var(--accent-ink);
  cursor: pointer;
  white-space: nowrap;
  transition: filter .14s, opacity .14s;
}
.btn-primary:hover:not(:disabled) { filter: brightness(1.08); }
.btn-primary:disabled { opacity: .45; cursor: not-allowed; }

.btn-quiet {
  font: inherit;
  font-size: var(--t-body);
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--s2);
  height: 34px;
  padding: 0 var(--s3);
  border-radius: var(--r-sm);
  border: 1px solid transparent;
  background: transparent;
  color: var(--ink-dim);
  cursor: pointer;
  white-space: nowrap;
  transition: background .14s, color .14s;
}
.btn-quiet:hover:not(:disabled) { background: var(--sunken); color: var(--ink); }
.btn-quiet:disabled { opacity: .45; cursor: not-allowed; }
.btn-quiet.btn-icon { width: 34px; padding: 0; }

/* ═══════════════════════════════════════════════════════════════════════════
   SETUP FORMS — the grouped Sound / Form / Feel layout shared by the loop and
   song builders inside the Setup drawer. Namespaced to .setup-form so the
   generic .group / .eyebrow names can't collide with other components.
   ═══════════════════════════════════════════════════════════════════════════ */
.setup-form .setup-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--s5);
  align-items: start;
}
.setup-form .group { display: flex; flex-direction: column; gap: var(--s3); min-width: 0; }
.setup-form .group > .eyebrow { padding-bottom: var(--s2); border-bottom: 1px solid var(--line); }

.setup-form details.advanced { margin-top: var(--s5); border-top: 1px solid var(--line); padding-top: var(--s4); }
.setup-form details.advanced > summary {
  cursor: pointer; font-size: var(--t-body); font-weight: 550; color: var(--ink-dim);
  list-style: none; display: flex; align-items: center; gap: var(--s2);
}
.setup-form details.advanced > summary::-webkit-details-marker { display: none; }
.setup-form details.advanced > summary::before { content: "›"; font-size: 16px; transition: rotate .16s; }
.setup-form details.advanced[open] > summary::before { rotate: 90deg; }
.setup-form details.advanced > summary:hover { color: var(--ink); }
.setup-form .adv-grid {
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--s5); margin-top: var(--s4); align-items: start;
}

@media (max-width: 860px) {
  .setup-form .setup-grid, .setup-form .adv-grid { grid-template-columns: 1fr; }
}

/* ═══════════════════════════════════════════════════════════════════════════
   FORM CONTROLS — global so every form re-skins at once.
   ═══════════════════════════════════════════════════════════════════════════ */
.generate-form { display: flex; flex-direction: column; gap: var(--s4); }

.field { display: flex; flex-direction: column; gap: var(--s1); }
.field label { font-size: var(--t-meta); font-weight: 500; color: var(--ink-dim); text-transform: none; letter-spacing: 0; }
.field .value { color: var(--accent); margin-left: 0.5rem; font-family: var(--f-mono); }

.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s3); }

select, input[type="number"], input[type="text"], input:not([type]), textarea {
  font: inherit;
  font-size: var(--t-body);
  background: var(--ground);
  border: 1px solid var(--line);
  color: var(--ink);
  padding: 0 var(--s2);
  height: 34px;
  border-radius: var(--r-sm);
  width: 100%;
  transition: border-color .14s;
}
textarea { height: auto; padding: var(--s2); line-height: 1.5; }
select:hover, input:hover, textarea:hover { border-color: var(--ink-faint); }

select::placeholder, input::placeholder, textarea::placeholder { color: var(--ink-faint); }

input[type="range"] { width: 100%; accent-color: var(--accent); cursor: pointer; }

.part-toggles { display: flex; gap: var(--s2); flex-wrap: wrap; }
.toggle {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: var(--t-meta);
  cursor: pointer;
  padding: 0.3rem 0.7rem;
  border: 1px solid var(--line);
  border-radius: 99px;
  color: var(--ink-dim);
  transition: border-color .14s, color .14s, background .14s;
}
.toggle:has(input:checked) { border-color: var(--accent-edge); background: var(--accent-wash); color: var(--accent); }

/* Legacy generate button — now just the primary look. */
.generate-btn { border-radius: var(--r-sm); }

.error-msg { color: var(--bad); font-size: var(--t-meta); margin-top: 0.5rem; }

/* ═══════════════════════════════════════════════════════════════════════════
   RESULT SURFACES — export panel + part cards
   ═══════════════════════════════════════════════════════════════════════════ */
.export-panel { display: flex; flex-direction: column; gap: var(--s4); }

.export-summary {
  display: flex;
  gap: var(--s5);
  font-size: var(--t-meta);
  color: var(--ink-dim);
  padding: var(--s3) var(--s4);
  background: var(--raised);
  border-radius: var(--r-md);
  border: 1px solid var(--line);
}

.gen-id { margin-left: auto; font-family: var(--f-mono); }

.part-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: var(--s3); }

.part-card {
  background: var(--raised);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: var(--s4);
  display: flex;
  flex-direction: column;
  gap: var(--s3);
}

.part-header { display: flex; flex-direction: column; gap: 0.2rem; }
.part-name { font-weight: 600; text-transform: capitalize; }
.part-file { font-size: var(--t-meta); color: var(--ink-faint); font-family: var(--f-mono); }

.download-btn {
  display: block;
  text-align: center;
  padding: 0.45rem;
  background: var(--sunken);
  color: var(--accent);
  border-radius: var(--r-sm);
  text-decoration: none;
  font-size: var(--t-meta);
  font-weight: 500;
  transition: background 0.14s;
}
.download-btn:hover { background: var(--surface-hover); }
</style>
