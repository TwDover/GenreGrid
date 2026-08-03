/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { shallowMount, flushPromises, type VueWrapper } from '@vue/test-utils'

// AudioClipCard leans on the audio-recorder/player/metronome composables and the
// audio-clip API; stub them so the card mounts headless (mirrors PartCard.test.ts).
// vi.mock factories are hoisted above the whole file, so the fakes have to be
// built inside vi.hoisted() (mirrors synthDrums.test.ts / useAudioRecorder.test.ts).
function fakeAudioBuffer(seconds = 1, sampleRate = 1000) {
  const length = Math.round(seconds * sampleRate)
  const data = new Float32Array(length)
  return { length, sampleRate, numberOfChannels: 1, getChannelData: () => data }
}

const {
  recorderStart, recorderStop, recorderCancel, decodeAndFit, listInputDevices, getLevel,
  playerToggle, playerStop, metroCountIn, metroSetMeter,
  saveAudioClip, deleteAudioClip,
} = vi.hoisted(() => ({
  recorderStart: vi.fn(async () => {}),
  recorderStop: vi.fn(async () => new Blob(['take'])),
  recorderCancel: vi.fn(),
  decodeAndFit: vi.fn(async (_blob: Blob, seconds: number) => fakeAudioBuffer(seconds)),
  listInputDevices: vi.fn(async () => [] as MediaDeviceInfo[]),
  getLevel: vi.fn(() => 0),
  playerToggle: vi.fn(async () => {}),
  playerStop: vi.fn(),
  metroCountIn: vi.fn(async () => 0),
  metroSetMeter: vi.fn(),
  saveAudioClip: vi.fn(async (req: { generation_id: string; start_bar: number; bars: number }) => ({
    part: 'audio' as const, filename: 'audio_clip.wav', url: `/exports/${req.generation_id}/audio_clip.wav`,
    start_bar: req.start_bar, bars: req.bars,
  })),
  deleteAudioClip: vi.fn(async () => {}),
}))

vi.mock('../composables/useAudioRecorder', () => ({
  useAudioRecorder: () => ({
    isRecording: ref(false), monitoring: ref(false), error: ref(null),
    start: recorderStart, stop: recorderStop, cancel: recorderCancel,
    setMonitoring: vi.fn(), decodeAndFit, listInputDevices, getLevel,
  }),
}))
// Self-contained like useAudioRecorder's mock above (not vi.hoisted): the ref
// and its toggle are created once, lazily, inside the factory — sharing one
// instance across every useMidiPlayer() call, same as the real singleton.
vi.mock('../composables/useMidiPlayer', () => {
  const audioClipMuted = ref(false)
  const toggleAudioClipMute = vi.fn(() => { audioClipMuted.value = !audioClipMuted.value })
  return {
    useMidiPlayer: () => ({ toggle: playerToggle, stop: playerStop, audioClipMuted, toggleAudioClipMute }),
  }
})
vi.mock('../composables/useMetronome', () => ({
  useMetronome: () => ({ countIn: metroCountIn, setMeter: metroSetMeter }),
}))
vi.mock('../services/api', () => ({
  saveAudioClip, deleteAudioClip, downloadUrl: (u: string) => u,
}))
vi.mock('../composables/useErrorLog', () => ({ logError: vi.fn() }))
// jsdom has no real Web Audio API — Tone.getTransport() would throw trying to
// build a real AudioContext, so it's faked here too (mirrors synthDrums.test.ts).
vi.mock('tone', () => ({
  getTransport: () => ({ bpm: { value: 0 } }),
  getContext: () => ({ rawContext: { decodeAudioData: async () => fakeAudioBuffer(1) } }),
}))

import AudioClipCard from './AudioClipCard.vue'
import { useMidiPlayer } from '../composables/useMidiPlayer'
import type { AudioClipInfo } from '../types/midi'
import type { EditorSection } from './PianoRollEditor.vue'

const { audioClipMuted, toggleAudioClipMute } = useMidiPlayer()

const sections: EditorSection[] = [
  { name: 'Verse', section_type: 'verse', start_bar: 0, bars: 8 },
  { name: 'Chorus', section_type: 'chorus', start_bar: 8, bars: 8 },
]

function mountCard(overrides: Partial<{
  generationId: string; bpm: number; clip: AudioClipInfo | null; playbackUrl: string
  sections: EditorSection[]; totalBars: number
}> = {}) {
  return shallowMount(AudioClipCard, {
    props: {
      generationId: 'gen1', bpm: 120, clip: null, playbackUrl: '/exports/gen1/song.mid',
      sections, ...overrides,
    },
  })
}

const recBtn = (w: VueWrapper) => w.findAll('button').find(b => b.text().includes('Rec'))
const saveBtn = (w: VueWrapper) => w.findAll('button').find(b => b.text().includes('Save'))
const discardBtn = (w: VueWrapper) => w.findAll('button').find(b => b.text() === '✕')
const deleteBtn = (w: VueWrapper) => w.findAll('button').find(b => b.text() === '🗑')
const muteBtn = (w: VueWrapper) => w.findAll('button').find(b => b.text() === 'M')

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, arrayBuffer: async () => new ArrayBuffer(8) }))
  for (const fn of [recorderStart, recorderStop, recorderCancel, decodeAndFit, listInputDevices, getLevel,
                    playerToggle, playerStop, metroCountIn, metroSetMeter, saveAudioClip, deleteAudioClip]) fn.mockClear()
  vi.mocked(toggleAudioClipMute).mockClear()
  audioClipMuted.value = false
  listInputDevices.mockResolvedValue([])
  getLevel.mockReturnValue(0)
})

describe('AudioClipCard — empty state', () => {
  it('shows a section picker and Rec button when no clip exists', async () => {
    const w = mountCard()
    await flushPromises()
    expect(w.find('.ac-section-select').exists()).toBe(true)
    expect(recBtn(w)).toBeTruthy()
  })

  it('loop mode (no sections) has no section picker', async () => {
    const w = mountCard({ sections: undefined, totalBars: 4 })
    await flushPromises()
    expect(w.find('.ac-section-select').exists()).toBe(false)
    expect(recBtn(w)).toBeTruthy()
  })

  it('hides the device picker when there is 0 or 1 input device', async () => {
    listInputDevices.mockResolvedValue([{ deviceId: 'default', label: 'Default' } as MediaDeviceInfo])
    const w = mountCard()
    await flushPromises()
    expect(w.find('.ac-device-select').exists()).toBe(false)
  })

  it('shows a device picker and records with the selected device when multiple exist', async () => {
    listInputDevices.mockResolvedValue([
      { deviceId: 'default', label: 'Default Mic' } as MediaDeviceInfo,
      { deviceId: 'usb-1', label: 'USB Headset' } as MediaDeviceInfo,
    ])
    const w = mountCard()
    await flushPromises()
    const select = w.find('.ac-device-select')
    expect(select.exists()).toBe(true)
    await select.setValue('usb-1')
    await recBtn(w)!.trigger('click')
    await flushPromises()
    expect(recorderStart).toHaveBeenCalledWith('usb-1')
  })
})

describe('AudioClipCard — record → review → save', () => {
  it('arming counts in, starts the recorder, and plays the selected section region', async () => {
    const w = mountCard()
    await flushPromises()
    await recBtn(w)!.trigger('click')
    await flushPromises()

    expect(metroCountIn).toHaveBeenCalled()
    expect(recorderStart).toHaveBeenCalled()
    // Verse is section 0: start_bar 0, bars 8, 4 beats/bar, 120 BPM -> 0..16s
    expect(playerToggle).toHaveBeenCalledWith(
      '/exports/gen1/song.mid', undefined, 'Recording', false, { start: 0, end: 16 },
    )
    expect(w.text()).toContain('Recording')
  })

  it('shows a live input-level meter while recording, polling getLevel()', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      getLevel.mockReturnValue(0.75)
      const w = mountCard()
      await flushPromises()
      await recBtn(w)!.trigger('click')
      await flushPromises()
      await vi.advanceTimersByTimeAsync(100)
      await flushPromises()
      const fill = w.find('.ac-meter-fill')
      expect(fill.exists()).toBe(true)
      expect(fill.attributes('style')).toContain('75%')
    } finally {
      vi.useRealTimers()
    }
  })

  it('records into the SECOND section when selected', async () => {
    const w = mountCard()
    await flushPromises()
    await w.find('.ac-section-select').setValue('1')
    await recBtn(w)!.trigger('click')
    await flushPromises()
    // Chorus: start_bar 8 -> 16s, bars 8 -> 16s duration -> 16..32
    expect(playerToggle).toHaveBeenCalledWith(
      '/exports/gen1/song.mid', undefined, 'Recording', false, { start: 16, end: 32 },
    )
  })

  it('stopping mid-take stops playback, decodes+fits the buffer, and shows Save/Discard', async () => {
    const w = mountCard()
    await flushPromises()
    await recBtn(w)!.trigger('click')
    await flushPromises()

    await (w.vm as unknown as { stopAndReview(): Promise<void> }).stopAndReview()
    await flushPromises()

    expect(playerStop).toHaveBeenCalled()
    expect(recorderStop).toHaveBeenCalled()
    expect(decodeAndFit).toHaveBeenCalledWith(expect.any(Blob), 16)   // Verse region duration
    expect(saveBtn(w)).toBeTruthy()
    expect(discardBtn(w)).toBeTruthy()
  })

  it('Save uploads the take with its placement and emits saved', async () => {
    const w = mountCard()
    await flushPromises()
    await recBtn(w)!.trigger('click')
    await flushPromises()
    await (w.vm as unknown as { stopAndReview(): Promise<void> }).stopAndReview()
    await flushPromises()

    await saveBtn(w)!.trigger('click')
    await flushPromises()

    expect(saveAudioClip).toHaveBeenCalledWith(expect.objectContaining({
      generation_id: 'gen1', start_bar: 0, bars: 8, file: expect.any(Blob),
    }))
    expect(w.emitted('saved')?.[0]).toEqual([{
      part: 'audio', filename: 'audio_clip.wav', url: '/exports/gen1/audio_clip.wav', start_bar: 0, bars: 8,
    }])
  })

  it('Discard drops the take without calling the API', async () => {
    const w = mountCard()
    await flushPromises()
    await recBtn(w)!.trigger('click')
    await flushPromises()
    await (w.vm as unknown as { stopAndReview(): Promise<void> }).stopAndReview()
    await flushPromises()

    await discardBtn(w)!.trigger('click')
    await flushPromises()

    expect(saveAudioClip).not.toHaveBeenCalled()
    expect(recBtn(w)).toBeTruthy()   // back to the empty/record state
  })
})

describe('AudioClipCard — existing clip', () => {
  const clip: AudioClipInfo = { part: 'audio', filename: 'audio_clip.wav', url: '/exports/gen1/audio_clip.wav', start_bar: 8, bars: 8 }

  it('shows placement, re-record, and delete controls', async () => {
    const w = mountCard({ clip })
    await flushPromises()
    expect(w.text()).toContain('Chorus')   // resolved from the section matching start_bar
    expect(w.findAll('button').some(b => b.text().includes('Re-rec'))).toBe(true)
    expect(deleteBtn(w)).toBeTruthy()
  })

  it('delete calls the API and emits deleted', async () => {
    const w = mountCard({ clip })
    await flushPromises()
    await deleteBtn(w)!.trigger('click')
    await flushPromises()
    expect(deleteAudioClip).toHaveBeenCalledWith('gen1')
    expect(w.emitted('deleted')).toBeTruthy()
  })

  it('mute toggles the shared player-level mute state', async () => {
    const w = mountCard({ clip })
    await flushPromises()
    const btn = muteBtn(w)!
    expect(btn.classes()).not.toContain('muted')
    await btn.trigger('click')
    expect(toggleAudioClipMute).toHaveBeenCalled()
    expect(muteBtn(w)!.classes()).toContain('muted')
  })
})
