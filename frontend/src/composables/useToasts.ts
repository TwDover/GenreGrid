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

export type ToastKind = 'success' | 'error'

export interface Toast {
  id: number
  message: string
  kind: ToastKind
}

// Module-level state so every component shares one toast stack
const toasts = ref<Toast[]>([])
let _nextId = 0

const SUCCESS_MS = 3500
const ERROR_MS = 6000

export function useToasts() {
  function dismiss(id: number) {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  function toast(message: string, kind: ToastKind = 'success') {
    const id = ++_nextId
    toasts.value = [...toasts.value, { id, message, kind }]
    setTimeout(() => dismiss(id), kind === 'error' ? ERROR_MS : SUCCESS_MS)
  }

  return { toasts, toast, dismiss }
}
