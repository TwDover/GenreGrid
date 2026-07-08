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

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
}

.app-header {
  padding: 2rem 2rem 1rem;
  border-bottom: 1px solid var(--panel-alt);
}

.app-header h1 {
  font-size: 2rem;
  font-weight: 700;
  letter-spacing: -0.5px;
  background: linear-gradient(135deg, var(--accent), var(--success));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.subtitle {
  font-size: 0.85rem;
  color: var(--text-faint);
  margin-top: 0.25rem;
}

.app-main {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 2rem;
  max-width: 1150px;
}

.mode-body {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 2rem;
  align-items: start;
}

/* Form styles */
.generate-form { display: flex; flex-direction: column; gap: 1rem; }

.field { display: flex; flex-direction: column; gap: 0.35rem; }
.field label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-dim); }
.field .value { color: var(--accent); margin-left: 0.5rem; }

.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }

select, input[type="number"], input[type="text"], input:not([type]), textarea {
  background: var(--panel);
  border: 1px solid var(--surface);
  color: var(--text);
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  font-size: 0.9rem;
  width: 100%;
}

/* Browser UA placeholder color defaults to a near-black gray — pin it to the
 * theme's dim text color so it's legible on dark AND light/retro. */
select::placeholder, input::placeholder, textarea::placeholder {
  color: var(--text-faint);
}

input[type="range"] {
  width: 100%;
  accent-color: var(--accent);
}

.part-toggles { display: flex; gap: 0.75rem; flex-wrap: wrap; }
.toggle {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
  cursor: pointer;
  padding: 0.35rem 0.75rem;
  border: 1px solid var(--surface);
  border-radius: 20px;
  transition: border-color 0.15s;
}
.toggle:has(input:checked) { border-color: var(--accent); color: var(--accent); }

.generate-btn {
  background: linear-gradient(135deg, var(--accent-dim), var(--success));
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  margin-top: 0.5rem;
  transition: opacity 0.15s;
}
.generate-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.generate-btn:not(:disabled):hover { opacity: 0.9; }

.error-msg { color: var(--error); font-size: 0.85rem; margin-top: 0.5rem; }

/* Export panel */
.export-panel { display: flex; flex-direction: column; gap: 1.25rem; }

.export-summary {
  display: flex;
  gap: 1.25rem;
  font-size: 0.85rem;
  color: var(--text-dim);
  padding: 0.75rem 1rem;
  background: var(--panel);
  border-radius: 8px;
  border: 1px solid var(--surface);
}

.gen-id { margin-left: auto; font-family: monospace; }

.part-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.75rem; }

.part-card {
  background: var(--panel);
  border: 1px solid var(--surface);
  border-radius: 10px;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.part-header { display: flex; flex-direction: column; gap: 0.2rem; }
.part-name { font-weight: 600; text-transform: capitalize; }
.part-file { font-size: 0.75rem; color: var(--text-faint); font-family: monospace; }

.download-btn {
  display: block;
  text-align: center;
  padding: 0.45rem;
  background: var(--surface);
  color: var(--accent);
  border-radius: 6px;
  text-decoration: none;
  font-size: 0.82rem;
  font-weight: 500;
  transition: background 0.15s;
}
.download-btn:hover { background: var(--surface-hover); }

@media (max-width: 700px) {
  .app-main {
    padding: 1rem;
    gap: 1.5rem;
  }
  .mode-body {
    grid-template-columns: 1fr;
  }
  .app-header {
    padding: 1rem 1rem 0.75rem;
  }
  .app-header h1 {
    font-size: 1.4rem;
  }
}

@media (max-width: 400px) {
  .app-main { padding: 0.75rem; }
}
</style>
