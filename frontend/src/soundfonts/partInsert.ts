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
import * as Tone from 'tone'
import { getMelodicBus, getBassBus, getDrumBus } from './loader'
import type { PlayerPart } from '../composables/playerConstants'
import { resolveToneValues, saturationCurveSamples, type PartTone } from './partTone'

// ── Per-part live output insert (roadmap 9.3) ────────────────────────────────
// One persistent Gain -> Panner per song part, sitting between that part's
// voice(s) (synth, sampler, piano fallback, custom instrument — whichever one
// a given song ends up using) and the shared family bus it already fed
// directly (getMelodicBus/getBassBus/getDrumBus, unchanged). Every voice for a
// part connects to its insert's .gain instead of the bus, so volume/pan
// automation applies uniformly regardless of which underlying voice is in use.
//
// Persistent (module-level, like loader.ts's buses) rather than rebuilt per
// play: several of the voices that can end up behind an insert (the piano
// fallback, an identity sampler) are ALSO persistent, cached-once-per-session
// instruments with a single fixed `.connect()` wired at load time — so the
// insert they feed has to be stable across plays too. resetPartInsert() clears
// a previous song's automation at the start of every new play.
export interface PartInsert {
  gain: Tone.Gain
  panner: Tone.Panner
  toneLow: Tone.Filter
  toneHigh: Tone.Filter
  toneSat: Tone.WaveShaper
}

const inserts: Partial<Record<PlayerPart, PartInsert>> = {}

function busFor(part: PlayerPart): Tone.ToneAudioNode {
  if (part === 'bass') return getBassBus()
  if (part === 'drums') return getDrumBus()
  return getMelodicBus()
}

export function getPartInsert(part: PlayerPart): PartInsert {
  const existing = inserts[part]
  if (existing) return existing
  // voice → gain → panner → toneLow → toneHigh → toneSat → bus (roadmap 6.5's
  // per-part tone preset sits at the tail of the existing 9.3 gain/pan insert, the
  // one point every voice type — sampled, synth-patch, custom instrument, synth
  // kit — already converges on before its family bus).
  const toneSat = new Tone.WaveShaper(x => x, 1024).connect(busFor(part))
  const toneHigh = new Tone.Filter({ type: 'highshelf', frequency: 3500, gain: 0 }).connect(toneSat)
  const toneLow = new Tone.Filter({ type: 'lowshelf', frequency: 120, gain: 0 }).connect(toneHigh)
  const panner = new Tone.Panner(0).connect(toneLow)
  const gain = new Tone.Gain(1).connect(panner)
  const created: PartInsert = { gain, panner, toneLow, toneHigh, toneSat }
  inserts[part] = created
  return created
}

/** Apply a per-part tone preset (roadmap 6.5) to a part's persistent insert.
 *  Call at the start of every play, like resetPartInsert. */
export function applyPartTone(part: PlayerPart, tone: PartTone): void {
  const insert = getPartInsert(part)
  const { lowShelfDb, highShelfDb, drive } = resolveToneValues(tone)
  const now = Tone.getContext().currentTime
  insert.toneLow.gain.cancelScheduledValues(now)
  insert.toneLow.gain.setTargetAtTime(lowShelfDb, now, 0.02)
  insert.toneHigh.gain.cancelScheduledValues(now)
  insert.toneHigh.gain.setTargetAtTime(highShelfDb, now, 0.02)
  insert.toneSat.curve = saturationCurveSamples(drive)
}

/** Reset a part's insert to flat/centered and clear any scheduled automation.
 *  Call once per part at the start of every play, before this song's static
 *  pan or automation curve (if any) is applied — otherwise a previous song's
 *  schedule could bleed into the next one on these persistent nodes. */
export function resetPartInsert(part: PlayerPart): void {
  const insert = getPartInsert(part)
  const now = Tone.getContext().currentTime
  insert.gain.gain.cancelScheduledValues(now)
  insert.gain.gain.value = 1
  insert.panner.pan.cancelScheduledValues(now)
  insert.panner.pan.value = 0
}
