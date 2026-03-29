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
  background: #0f0f13;
  color: #e0e0e8;
  min-height: 100vh;
}

.app-header {
  padding: 2rem 2rem 1rem;
  border-bottom: 1px solid #1e1e2e;
}

.app-header h1 {
  font-size: 2rem;
  font-weight: 700;
  letter-spacing: -0.5px;
  background: linear-gradient(135deg, #a78bfa, #60a5fa);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.subtitle {
  font-size: 0.85rem;
  color: #6b6b80;
  margin-top: 0.25rem;
}

.app-main {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 2rem;
  padding: 2rem;
  max-width: 1100px;
}

/* Form styles */
.generate-form { display: flex; flex-direction: column; gap: 1rem; }

.field { display: flex; flex-direction: column; gap: 0.35rem; }
.field label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; color: #8888a0; }
.field .value { color: #a78bfa; margin-left: 0.5rem; }

.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }

select, input[type="number"] {
  background: #1a1a24;
  border: 1px solid #2a2a3e;
  color: #e0e0e8;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  font-size: 0.9rem;
  width: 100%;
}

input[type="range"] {
  width: 100%;
  accent-color: #a78bfa;
}

.part-toggles { display: flex; gap: 0.75rem; flex-wrap: wrap; }
.toggle {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
  cursor: pointer;
  padding: 0.35rem 0.75rem;
  border: 1px solid #2a2a3e;
  border-radius: 20px;
  transition: border-color 0.15s;
}
.toggle:has(input:checked) { border-color: #a78bfa; color: #a78bfa; }

.generate-btn {
  background: linear-gradient(135deg, #7c3aed, #2563eb);
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

.error-msg { color: #f87171; font-size: 0.85rem; margin-top: 0.5rem; }

/* Export panel */
.export-panel { display: flex; flex-direction: column; gap: 1.25rem; }

.export-summary {
  display: flex;
  gap: 1.25rem;
  font-size: 0.85rem;
  color: #8888a0;
  padding: 0.75rem 1rem;
  background: #1a1a24;
  border-radius: 8px;
  border: 1px solid #2a2a3e;
}

.gen-id { margin-left: auto; font-family: monospace; }

.part-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.75rem; }

.part-card {
  background: #1a1a24;
  border: 1px solid #2a2a3e;
  border-radius: 10px;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.part-header { display: flex; flex-direction: column; gap: 0.2rem; }
.part-name { font-weight: 600; text-transform: capitalize; }
.part-file { font-size: 0.75rem; color: #6b6b80; font-family: monospace; }

.download-btn {
  display: block;
  text-align: center;
  padding: 0.45rem;
  background: #2a2a3e;
  color: #a78bfa;
  border-radius: 6px;
  text-decoration: none;
  font-size: 0.82rem;
  font-weight: 500;
  transition: background 0.15s;
}
.download-btn:hover { background: #3a3a54; }

@media (max-width: 700px) {
  .app-main {
    grid-template-columns: 1fr;
    padding: 1rem;
    gap: 1.5rem;
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
