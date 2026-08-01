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
import { describe, it, expect, vi } from 'vitest'
import { drumTriggerCallback, voiceTriggerCallback } from './scheduler'

describe('drumTriggerCallback', () => {
  it('triggers the kit with (midi, velocity, time) when unmuted', () => {
    const kit = { trigger: vi.fn() }
    const duck = vi.fn()
    const cb = drumTriggerCallback(kit, () => false, false, duck)
    cb(1.5, { midi: 38, velocity: 0.8 })
    expect(kit.trigger).toHaveBeenCalledWith(38, 0.8, 1.5)
    expect(duck).not.toHaveBeenCalled()
  })

  it('does nothing when the drums part is muted', () => {
    const kit = { trigger: vi.fn() }
    const duck = vi.fn()
    const cb = drumTriggerCallback(kit, () => true, true, duck)
    cb(0, { midi: 36, velocity: 1 })
    expect(kit.trigger).not.toHaveBeenCalled()
    expect(duck).not.toHaveBeenCalled()
  })

  it('ducks on the kick (midi 36) only when pump is on', () => {
    const kit = { trigger: vi.fn() }
    const duck = vi.fn()
    drumTriggerCallback(kit, () => false, true, duck)(2, { midi: 36, velocity: 1 })
    expect(duck).toHaveBeenCalledWith(2)
  })

  it('does not duck on non-kick hits, even with pump on', () => {
    const kit = { trigger: vi.fn() }
    const duck = vi.fn()
    drumTriggerCallback(kit, () => false, true, duck)(2, { midi: 42, velocity: 1 })  // hat
    expect(kit.trigger).toHaveBeenCalled()
    expect(duck).not.toHaveBeenCalled()
  })

  it('does not duck when pump is off, even on a kick', () => {
    const kit = { trigger: vi.fn() }
    const duck = vi.fn()
    drumTriggerCallback(kit, () => false, false, duck)(2, { midi: 36, velocity: 1 })
    expect(duck).not.toHaveBeenCalled()
  })

  it('scales velocity by the live level, re-read per hit, and skips at zero', () => {
    const kit = { trigger: vi.fn() }
    let level = 0.5
    const cb = drumTriggerCallback(kit, () => false, false, vi.fn(), () => level)
    cb(0, { midi: 38, velocity: 0.8 })
    expect(kit.trigger).toHaveBeenCalledWith(38, 0.8 * 0.5, 0)
    level = 0
    cb(1, { midi: 38, velocity: 0.8 })
    expect(kit.trigger).toHaveBeenCalledTimes(1)
  })

  it('re-reads mute state per call (mute mid-playback stops later hits)', () => {
    const kit = { trigger: vi.fn() }
    let muted = false
    const cb = drumTriggerCallback(kit, () => muted, false, vi.fn())
    cb(0, { midi: 38, velocity: 1 })
    muted = true
    cb(1, { midi: 38, velocity: 1 })
    expect(kit.trigger).toHaveBeenCalledTimes(1)
  })
})

describe('voiceTriggerCallback', () => {
  it('plays the note (midi->name, duration, time, velocity) when unmuted', () => {
    const voice = { triggerAttackRelease: vi.fn() }
    const midiToNote = (m: number) => `N${m}`
    const cb = voiceTriggerCallback(voice, () => false, midiToNote)
    cb(3.25, { midi: 60, duration: 0.5, velocity: 0.7 })
    expect(voice.triggerAttackRelease).toHaveBeenCalledWith('N60', 0.5, 3.25, 0.7)
  })

  it('does nothing when the part is muted', () => {
    const voice = { triggerAttackRelease: vi.fn() }
    voiceTriggerCallback(voice, () => true, m => `N${m}`)(0, { midi: 60, duration: 1, velocity: 1 })
    expect(voice.triggerAttackRelease).not.toHaveBeenCalled()
  })

  it('scales velocity by the live level and skips at zero', () => {
    const voice = { triggerAttackRelease: vi.fn() }
    let level = 0.25
    const cb = voiceTriggerCallback(voice, () => false, m => `N${m}`, () => level)
    cb(1, { midi: 60, duration: 0.5, velocity: 0.8 })
    expect(voice.triggerAttackRelease).toHaveBeenCalledWith('N60', 0.5, 1, 0.8 * 0.25)
    level = 0
    cb(2, { midi: 60, duration: 0.5, velocity: 0.8 })
    expect(voice.triggerAttackRelease).toHaveBeenCalledTimes(1)
  })
})
