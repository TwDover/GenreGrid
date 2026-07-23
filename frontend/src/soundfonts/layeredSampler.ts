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

// ── Multi-velocity / round-robin sampler ─────────────────────────────────────
// Tone.Sampler maps one file per note-zone and only scales that file's gain by
// note velocity — so a soft and a hard hit sound identical but louder, which reads
// as synthetic, and a repeated note replays the exact same sample ("machine-gun"
// effect). LayeredSampler wraps several Tone.Samplers to add the two things real
// instruments have and Tone.Sampler lacks:
//
//   • Velocity layers — separate samples recorded (or filtered) at different
//     dynamics; the incoming note velocity picks the layer, so timbre changes with
//     dynamics, not just level.
//   • Round-robins — several alternate samples for the same note+layer, cycled per
//     hit so repeated notes don't machine-gun.
//
// It is a drop-in for the call sites' Tone.Sampler surface (triggerAttackRelease /
// connect / disconnect / dispose) and degrades to exactly one inner Tone.Sampler
// when handed a single-layer, single-round-robin set — so the legacy sample sets
// keep working byte-for-byte until a `velocity.json` manifest adds layers.

/** One velocity layer: an upper velocity bound plus the note→file(s) for it.
 *  A string value is a single sample; an array is that note's round-robins. */
export interface VelocityLayer {
  /** Inclusive upper bound in Tone's 0..1 velocity range. The top layer should be 1. */
  maxVelocity: number
  urls: Record<string, string | string[]>
}

export interface LayeredSamplerManifest {
  /** Velocity layers; order in the file does not matter — they are sorted ascending. */
  layers: VelocityLayer[]
}

export interface LayeredSamplerOptions {
  baseUrl: string
  volume?: number
  context?: Tone.BaseContext
  /** Multi-layer set. Mutually exclusive with `legacyUrls`. */
  manifest?: LayeredSamplerManifest
  /** Single-layer legacy set: a plain note→file map (the pre-manifest format). */
  legacyUrls?: Record<string, string>
}

// A layer normalized for playback: its velocity ceiling and one Tone.Sampler per
// round-robin slot (samplers[i] holds the i-th alternate of every note).
interface LoadedLayer {
  maxVelocity: number
  samplers: Tone.Sampler[]
}

// ── Pure helpers (unit-tested; no AudioContext needed) ───────────────────────

/** Turn a manifest (or a legacy map) into layers sorted ascending by ceiling.
 *  The returned layers always cover the full range — the top one is forced to 1. */
export function normalizeLayers(opts: Pick<LayeredSamplerOptions, 'manifest' | 'legacyUrls'>): VelocityLayer[] {
  if (opts.manifest && opts.manifest.layers.length > 0) {
    const layers = [...opts.manifest.layers].sort((a, b) => a.maxVelocity - b.maxVelocity)
    // Guarantee the loudest layer catches velocity 1.0 no matter how it was authored.
    layers[layers.length - 1] = { ...layers[layers.length - 1], maxVelocity: 1 }
    return layers
  }
  return [{ maxVelocity: 1, urls: opts.legacyUrls ?? {} }]
}

/** Pick the layer index for a velocity: the lowest layer whose ceiling covers it,
 *  clamped to the top layer for anything at or above the last ceiling. */
export function selectLayerIndex(layers: Pick<VelocityLayer, 'maxVelocity'>[], velocity: number): number {
  for (let i = 0; i < layers.length; i++) {
    if (velocity <= layers[i].maxVelocity) return i
  }
  return layers.length - 1
}

/** How many round-robin slots a layer needs: the widest note's alternate count. */
export function roundRobinWidth(layer: VelocityLayer): number {
  let width = 1
  for (const v of Object.values(layer.urls)) {
    if (Array.isArray(v)) width = Math.max(width, v.length)
  }
  return width
}

/** The note→file map for one round-robin slot of a layer. Notes with fewer
 *  alternates than `rrIndex` reuse their last one, so uneven RR counts are fine. */
export function urlsForRoundRobin(layer: VelocityLayer, rrIndex: number): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [note, v] of Object.entries(layer.urls)) {
    if (Array.isArray(v)) out[note] = v[Math.min(rrIndex, v.length - 1)]
    else out[note] = v
  }
  return out
}

// ── The sampler ──────────────────────────────────────────────────────────────

export class LayeredSampler {
  /** Resolves once every inner Tone.Sampler has loaded its buffers. */
  readonly loaded: Promise<void>
  private layers: LoadedLayer[] = []
  private rr = 0
  private disposed = false

  constructor(opts: LayeredSamplerOptions) {
    const normalized = normalizeLayers(opts)
    const pending: Promise<void>[] = []

    for (const layer of normalized) {
      const width = roundRobinWidth(layer)
      const samplers: Tone.Sampler[] = []
      for (let rr = 0; rr < width; rr++) {
        pending.push(
          new Promise<void>((resolve, reject) => {
            const sampler = new Tone.Sampler({
              ...(opts.context ? { context: opts.context } : {}),
              urls: urlsForRoundRobin(layer, rr),
              baseUrl: opts.baseUrl,
              volume: opts.volume ?? 0,
              onload: () => resolve(),
              onerror: reject,
            })
            samplers.push(sampler)
          }),
        )
      }
      this.layers.push({ maxVelocity: layer.maxVelocity, samplers })
    }

    this.loaded = Promise.all(pending).then(() => undefined)
  }

  /** Play a note, choosing the velocity layer and cycling the layer's round-robins. */
  triggerAttackRelease(
    note: Tone.Unit.Frequency,
    duration: Tone.Unit.Time,
    time?: Tone.Unit.Time,
    velocity = 1,
  ): this {
    const layer = this.layers[selectLayerIndex(this.layers, velocity)]
    if (layer) {
      const sampler = layer.samplers[this.rr++ % layer.samplers.length]
      sampler.triggerAttackRelease(note, duration, time, velocity)
    }
    return this
  }

  /** Route every inner sampler to the destination (they sum there). */
  connect(destination: Tone.InputNode): this {
    for (const layer of this.layers) for (const s of layer.samplers) s.connect(destination)
    return this
  }

  disconnect(destination?: Tone.InputNode): this {
    for (const layer of this.layers) {
      for (const s of layer.samplers) {
        if (destination) s.disconnect(destination)
        else s.disconnect()
      }
    }
    return this
  }

  dispose(): this {
    if (this.disposed) return this
    this.disposed = true
    for (const layer of this.layers) for (const s of layer.samplers) s.dispose()
    return this
  }
}

// How many velocity layers this instrument actually loaded (1 = legacy set).
// Exposed for logging/diagnostics.
export function layerCount(sampler: LayeredSampler): number {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (sampler as any).layers.length
}

/**
 * Load a sample set that may or may not have velocity layers yet. Looks for a
 * `velocity.json` manifest under `baseUrl`; if present the set plays with velocity
 * layers + round-robins, otherwise it falls back to the passed single-layer map so
 * instruments that haven't been re-sampled keep working unchanged.
 *
 * `baseUrl` must end in '/'. `legacyUrls` is the pre-manifest note→file map.
 */
export async function loadLayeredSampler(opts: {
  baseUrl: string
  legacyUrls: Record<string, string>
  volume?: number
  context?: Tone.BaseContext
}): Promise<LayeredSampler> {
  let manifest: LayeredSamplerManifest | undefined
  try {
    const res = await fetch(`${opts.baseUrl}velocity.json`, { cache: 'force-cache' })
    if (res.ok) {
      const parsed = (await res.json()) as LayeredSamplerManifest
      if (parsed && Array.isArray(parsed.layers) && parsed.layers.length > 0) manifest = parsed
    }
  } catch {
    // No manifest (404 / offline / parse error) — fall back to the legacy single layer.
  }

  const sampler = new LayeredSampler({
    baseUrl: opts.baseUrl,
    volume: opts.volume,
    context: opts.context,
    manifest,
    legacyUrls: manifest ? undefined : opts.legacyUrls,
  })
  await sampler.loaded
  return sampler
}
