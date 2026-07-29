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
import { describe, it, expect, beforeEach } from 'vitest'
import { isReactive } from 'vue'
import { useCustomInstruments } from './useCustomInstruments'

// Regression guard for the Electron IPC "An object could not be cloned" bug found in
// the custom-instruments desktop runtime pass: `updateKitSlot` re-saves an instrument it
// read back out of the reactive store, so the object (and its nested manifests) are Vue
// reactive Proxies. Electron's structured-clone IPC rejects those, which silently broke
// kit editing in the packaged app. The store must strip the object to plain data first.
// This test mocks the storage IPC and asserts the payload handed to it is proxy-free.

interface SavedInst { id: string; kit?: Record<string, unknown> }
let saved: SavedInst[] = []
const disk: Record<string, { name: string; data: number[] }[]> = {}

beforeEach(() => {
  saved = []
  ;(window as unknown as { electronAPI: unknown }).electronAPI = {
    instruments: {
      list: async () => [],
      save: async (inst: SavedInst, files: { name: string; data: number[] }[]) => {
        saved.push(inst)
        if (files.length) disk[inst.id] = files
      },
      remove: async () => {},
      read: async (id: string) => disk[id] ?? [],
    },
  }
  localStorage.clear()
})

describe('useCustomInstruments — IPC payload is structured-clone safe', () => {
  it('updateKitSlot sends a plain (non-reactive) instrument to the storage IPC', async () => {
    const store = useCustomInstruments()
    const kick = new File([new Uint8Array(2048).fill(7)], 'kick.wav', { type: 'audio/wav' })
    const res = await store.importInstrument('Regression Kit', 'drums', [kick])
    expect(res).toBeTruthy()
    const id = res!.instrument.id

    saved = [] // ignore the import save; we care about the re-save path
    // Place the stored file into a second (empty) slot — the exact call the kit editor makes.
    await store.updateKitSlot(id, 38 /* snare */, ['kick.wav'])

    expect(saved.length).toBe(1)
    const payload = saved[0]
    // The top object and every nested kit-piece manifest must be plain, or Electron's
    // structured-clone IPC throws "An object could not be cloned".
    expect(isReactive(payload)).toBe(false)
    expect(isReactive(payload.kit)).toBe(false)
    for (const piece of Object.values(payload.kit ?? {})) {
      expect(isReactive(piece)).toBe(false)
    }
    // And it must actually survive a structured clone.
    expect(() => structuredClone(payload)).not.toThrow()
  })
})
