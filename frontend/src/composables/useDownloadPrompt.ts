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

interface PromptState {
  active: boolean
  title: string
  defaultName: string   // base name, no extension
  extension: string      // e.g. "mid", "wav" — shown as a fixed suffix, not editable
}

// Module-scope so DownloadNamePrompt.vue (mounted once in HomePage) and every
// caller share one dialog instance instead of each needing its own modal.
const state = ref<PromptState>({ active: false, title: 'Save file', defaultName: '', extension: '' })
let _resolve: ((name: string | null) => void) | null = null

/** Characters invalid in Windows/macOS/Linux filenames, plus leading/trailing
 *  dots and spaces that some filesystems reject or silently strip. */
function sanitizeFilename(name: string): string {
  // Control chars (\x00-\x1f) are stripped on purpose — they're invalid in filenames.
  // eslint-disable-next-line no-control-regex
  const cleaned = name.replace(/[<>:"/\\|?*\x00-\x1f]/g, '').trim().replace(/\.+$/, '')
  return cleaned || 'export'
}

export function useDownloadPrompt() {
  /** Show the rename dialog; resolves to the sanitized base name (no extension),
   *  or null if the user cancelled. */
  function promptFilename(defaultName: string, extension: string, title = 'Save file'): Promise<string | null> {
    // A second prompt while one is open cancels the first rather than queuing —
    // there's only one modal, and only one export action happens at a time.
    _resolve?.(null)
    state.value = { active: true, title, defaultName: sanitizeFilename(defaultName), extension }
    return new Promise(resolve => { _resolve = resolve })
  }

  function confirm(name: string) {
    const resolved = _resolve
    state.value = { ...state.value, active: false }
    _resolve = null
    resolved?.(sanitizeFilename(name || state.value.defaultName))
  }

  function cancel() {
    const resolved = _resolve
    state.value = { ...state.value, active: false }
    _resolve = null
    resolved?.(null)
  }

  return { promptState: state, promptFilename, confirm, cancel }
}
