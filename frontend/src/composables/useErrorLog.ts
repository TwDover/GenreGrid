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

export interface ErrorLogEntry {
  id: number
  timestamp: string   // ISO 8601
  context: string     // where it came from, e.g. "WAV export", "Uncaught error"
  message: string
  stack?: string
}

const MAX_ENTRIES = 200
const STORAGE_KEY = 'genregrid_error_log'

function loadEntries(): ErrorLogEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* storage unavailable or corrupt — start fresh */ }
  return []
}

// Module-scope so every caller (deep in a component, or a global window
// handler) shares one log and one panel, the same pattern as useToasts /
// useDownloadPrompt.
const entries = ref<ErrorLogEntry[]>(loadEntries())
const isOpen = ref(false)
let nextId = entries.value.reduce((max, e) => Math.max(max, e.id), 0) + 1

function persist() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.value.slice(0, MAX_ENTRIES))) } catch { /* storage unavailable */ }
}

function extract(error: unknown): { message: string; stack?: string } {
  if (error instanceof Error) return { message: error.message, stack: error.stack }
  if (typeof error === 'string') return { message: error }
  try { return { message: JSON.stringify(error) } } catch { return { message: String(error) } }
}

/** Log an error with full context and stack trace (when available). Always
 *  also goes to the browser console; in the desktop app it's additionally
 *  appended to a file next to backend.log, so it survives even if no one
 *  opens the in-app panel before closing the window. */
export function logError(context: string, error: unknown): void {
  const { message, stack } = extract(error)
  const entry: ErrorLogEntry = { id: nextId++, timestamp: new Date().toISOString(), context, message, stack }
  entries.value = [entry, ...entries.value].slice(0, MAX_ENTRIES)
  persist()
  console.error(`[${context}]`, error)

  const api = (window as any).electronAPI
  if (api?.logRendererError) {
    api.logRendererError({ timestamp: entry.timestamp, context, message, stack }).catch(() => { /* best-effort */ })
  }
}

let handlersInstalled = false

/** Call once at app startup. Catches errors that never went through an
 *  explicit try/catch — a bug we didn't anticipate, not just ones we did. */
export function installGlobalErrorHandlers(): void {
  if (handlersInstalled) return
  handlersInstalled = true
  window.addEventListener('error', (e: ErrorEvent) => {
    logError('Uncaught error', e.error ?? e.message)
  })
  window.addEventListener('unhandledrejection', (e: PromiseRejectionEvent) => {
    logError('Unhandled promise rejection', e.reason)
  })
}

export function useErrorLog() {
  function clear() {
    entries.value = []
    persist()
  }
  function open() { isOpen.value = true }
  function close() { isOpen.value = false }
  return { entries, isOpen, logError, clear, open, close }
}
