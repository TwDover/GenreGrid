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

export const THEMES = ['dark', 'light', 'retro'] as const
export type Theme = typeof THEMES[number]

const THEME_META: Record<Theme, { icon: string; label: string }> = {
  dark:  { icon: '🌙', label: 'Dark' },
  light: { icon: '☀️', label: 'Light' },
  retro: { icon: '📟', label: 'Retro' },
}

function _load(): Theme {
  try {
    const t = localStorage.getItem('genregrid_theme')
    if (t && (THEMES as readonly string[]).includes(t)) return t as Theme
  } catch { /* storage unavailable */ }
  return 'dark'
}

const theme = ref<Theme>(_load())

function _apply(t: Theme) {
  document.documentElement.dataset.theme = t
}

// Apply at module load so the first paint is already themed (no flash)
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
export function themeColor(token: string, fallback = '#00c8ff'): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(token).trim()
  return v || fallback
}
