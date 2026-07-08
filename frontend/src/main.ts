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

console.log(
  '%cGenreGrid%c\nStyle-based MIDI generator\n%cCreated by TW Dover',
  'color:#00c8ff;font-size:22px;font-weight:700;letter-spacing:0.05em',
  'color:#4a7080;font-size:12px',
  'color:#2a6070;font-size:11px',
)

createApp(App).mount('#app')
