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
import { describe, it, expect, vi, afterEach } from 'vitest'
import { nextTick, ref } from 'vue'
import { mount, type DOMWrapper } from '@vue/test-utils'
import type { CustomInstrument } from '../soundfonts/customInstruments'

const instruments = ref<CustomInstrument[]>([])
const assignments = ref({ defaults: {} })
const panelOpen = ref(true)
const updateKitSlot = vi.fn()
vi.mock('../composables/useCustomInstruments', () => ({
  useCustomInstruments: () => ({
    instruments, assignments, panelOpen,
    supported: () => true,
    ensureLoaded: vi.fn(),
    importInstrument: vi.fn(),
    deleteInstrument: vi.fn(),
    assignPart: vi.fn(),
    getInstrument: (id: string) => instruments.value.find(i => i.id === id),
    materializeKit: vi.fn(),
    updateKitSlot,
    storedFileNames: vi.fn().mockResolvedValue(['kick_soft.wav', 'kick_hard.wav', 'kick_rr2.wav']),
  }),
}))
vi.mock('../composables/useStyleCatalog', () => ({
  useStyleCatalog: () => ({ catalog: ref(new Map()), activeStyleId: ref(null) }),
  instrumentLabel: () => null,
}))
vi.mock('../composables/useMixSettings', () => ({
  useMixSettings: () => ({ toneForPart: () => ({ preset: 'neutral', amount: 0 }), setPartTone: vi.fn() }),
}))
vi.mock('../soundfonts/drums', () => ({ drumCharacterForStyle: () => 'acoustic' }))
vi.mock('../soundfonts/audition', () => ({
  auditionPiece: vi.fn(), auditionSynthPiece: vi.fn(), disposeAudition: vi.fn(),
}))

import InstrumentsPanel from './InstrumentsPanel.vue'

// jsdom doesn't implement FileList assignment on a real <input>, so drive the
// change handler with a plain object shaped like the event onPick reads
// (e.target.files) rather than trying to set a real FileList.
function pick(input: DOMWrapper<Element>, files: File[]) {
  Object.defineProperty(input.element, 'files', { value: files, configurable: true })
  return input.trigger('change')
}

const file = (name: string) => new File(['x'], name)

describe('InstrumentsPanel — file-picker gating', () => {
  it('accepts only audio extensions in the "Choose files" OS dialog', () => {
    const wrapper = mount(InstrumentsPanel)
    const input = wrapper.findAll('input[type="file"]')[0]
    const accept = input.attributes('accept') ?? ''
    for (const ext of ['.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac']) {
      expect(accept).toContain(ext)
    }
  })

  it('filters non-audio files out of a selection and reports how many were skipped', async () => {
    const wrapper = mount(InstrumentsPanel)
    const input = wrapper.findAll('input[type="file"]')[0]
    await pick(input, [file('kick.wav'), file('readme.txt'), file('cover.png'), file('snare.mp3')])

    expect(wrapper.text()).toContain('2 file(s) selected')
    expect(wrapper.text()).toContain('2 non-audio file(s) skipped.')
  })

  it('selecting only audio files reports no skipped notice', async () => {
    const wrapper = mount(InstrumentsPanel)
    const input = wrapper.findAll('input[type="file"]')[0]
    await pick(input, [file('a.wav'), file('b.mp3')])

    expect(wrapper.text()).toContain('2 file(s) selected')
    expect(wrapper.text()).not.toContain('skipped')
  })

  it('a folder pick (no accept filter) still drops non-audio files client-side', async () => {
    const wrapper = mount(InstrumentsPanel)
    const folderInput = wrapper.findAll('input[type="file"]')[1]
    expect(folderInput.attributes('webkitdirectory')).toBeDefined()
    await pick(folderInput, [file('kick.wav'), file('.DS_Store'), file('Thumbs.db')])

    expect(wrapper.text()).toContain('1 file(s) selected')
    expect(wrapper.text()).toContain('2 non-audio file(s) skipped.')
  })

  it('selecting only non-audio files leaves nothing picked and import disabled', async () => {
    const wrapper = mount(InstrumentsPanel)
    const input = wrapper.findAll('input[type="file"]')[0]
    await pick(input, [file('readme.txt')])

    expect(wrapper.text()).not.toContain('file(s) selected')
    const addBtn = wrapper.findAll('button').find(b => b.text().includes('Add instrument'))!
    expect((addBtn.element as HTMLButtonElement).disabled).toBe(true)
  })
})

describe('InstrumentsPanel — multi-file kit slots', () => {
  const kickPitch = 36

  afterEach(() => {
    instruments.value = []
    updateKitSlot.mockClear()
  })

  async function openKitEditor() {
    instruments.value = [{
      id: 'kit-1',
      name: 'My Kit',
      kind: 'drums',
      manifest: { layers: [] },
      kit: {
        [kickPitch]: {
          layers: [
            { maxVelocity: 0.5, urls: { C4: 'kick_soft.wav' } },
            { maxVelocity: 1, urls: { C4: 'kick_hard.wav' } },
          ],
        },
      },
      createdAt: 0,
    }]
    const wrapper = mount(InstrumentsPanel)
    await wrapper.findAll('.ip-mini').find(b => b.text() === '✎ pieces')!.trigger('click')
    await nextTick()
    return wrapper
  }

  // DRUM_SLOTS renders all twelve pieces regardless of which the kit fills, so tests
  // must scope to the Kick row specifically rather than grabbing the first slot.
  function kickSlot(wrapper: Awaited<ReturnType<typeof openKitEditor>>) {
    return wrapper.findAll('.ip-slot').find(s => s.text().includes('Kick'))!
  }

  it('lists every file on a piece as a chip, across all its layers', async () => {
    const wrapper = await openKitEditor()
    const slot = kickSlot(wrapper)
    expect(slot.text()).toContain('kick_soft.wav')
    expect(slot.text()).toContain('kick_hard.wav')
  })

  it('only offers not-yet-assigned files in the "add" dropdown for that piece', async () => {
    const wrapper = await openKitEditor()
    const options = kickSlot(wrapper).find('select.ip-slot-add').findAll('option').map(o => o.attributes('value'))
    expect(options).not.toContain('kick_soft.wav')
    expect(options).not.toContain('kick_hard.wav')
    expect(options).toContain('kick_rr2.wav')
  })

  it('removing a chip drops just that file, keeping the rest of the piece intact', async () => {
    const wrapper = await openKitEditor()
    const chip = kickSlot(wrapper).findAll('.ip-chip').find(c => c.text().includes('kick_soft.wav'))!
    await chip.find('.ip-chip-x').trigger('click')
    expect(updateKitSlot).toHaveBeenCalledWith('kit-1', kickPitch, ['kick_hard.wav'])
  })

  it('adding a file appends it to the piece\'s existing files', async () => {
    const wrapper = await openKitEditor()
    const select = kickSlot(wrapper).find('select.ip-slot-add')
    await select.setValue('kick_rr2.wav')
    expect(updateKitSlot).toHaveBeenCalledWith('kit-1', kickPitch, ['kick_soft.wav', 'kick_hard.wav', 'kick_rr2.wav'])
  })
})
