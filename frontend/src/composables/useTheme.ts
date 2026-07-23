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
import { ref } from 'vue'

// Three visually distinct looks. There's deliberately no "system" cycle stop —
// it resolved to whichever of light/dark matched the OS, so one click appeared
// to do nothing and read as a bug. Instead the app DEFAULTS to the OS on first
// load (below), then the toggle cycles these explicit themes.
//   · light     — calm neutral (cool grey, cyan accent)
//   · dark      — calm neutral, dark
//   · whimsical — a warm "Sunset" theme, just for fun
export const THEMES = ['light', 'dark', 'whimsical'] as const
export type Theme = typeof THEMES[number]

export const THEME_META: Record<Theme, { icon: string; label: string }> = {
  light:     { icon: '☀', label: 'Light' },
  dark:      { icon: '☾', label: 'Dark' },
  whimsical: { icon: '🌅', label: 'Sunset' },
}

function _osPrefersDark(): boolean {
  return typeof matchMedia !== 'undefined' && matchMedia('(prefers-color-scheme: dark)').matches
}

function _load(): Theme {
  try {
    const t = localStorage.getItem('genregrid_theme')
    if (t && (THEMES as readonly string[]).includes(t)) return t as Theme
  } catch { /* storage unavailable */ }
  // No saved choice yet → follow the OS to a degree.
  return _osPrefersDark() ? 'dark' : 'light'
}

const theme = ref<Theme>(_load())

function _apply(t: Theme) {
  document.documentElement.dataset.theme = t
}

// Apply at module load so the first paint is already themed (no flash).
_apply(theme.value)

export function useTheme() {
  function setTheme(t: Theme) {
    theme.value = t
    _apply(t)
    try { localStorage.setItem('genregrid_theme', t) } catch { /* storage unavailable */ }
  }

  function cycleTheme() {
    const next = THEMES[(THEMES.indexOf(theme.value) + 1) % THEMES.length]
    setTheme(next)
  }

  return { theme, setTheme, cycleTheme, THEME_META }
}

/** Read a theme token's current value — for canvas/SVG code that can't use
 *  var() in a CSS context (e.g. PianoRoll's 2D canvas). */
export function themeColor(token: string, fallback = '#45c8e8'): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(token).trim()
  return v || fallback
}
