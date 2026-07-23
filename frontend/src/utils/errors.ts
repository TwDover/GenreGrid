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

// A `catch` binding is typed `unknown`, so reaching for `.message` needs a
// guard. This mirrors the old `e.message ?? fallback` idiom used across the UI:
// return the string message off an Error (or any object carrying a string
// `message`, e.g. an Axios error), otherwise undefined so the caller's `??`
// fallback kicks in.
export function errorMessage(e: unknown): string | undefined {
  if (e instanceof Error) return e.message
  if (typeof e === 'object' && e !== null && 'message' in e) {
    const m = (e as { message: unknown }).message
    if (typeof m === 'string') return m
  }
  return undefined
}
