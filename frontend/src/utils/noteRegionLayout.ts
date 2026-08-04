/*
 * GenreGrid — a style-based MIDI generator.
 * Copyright (C) 2026 Tw Dover
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License v3 or (at your option) any later
 * version. Distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.
 */
// Pure geometry for the per-part note-region timeline strip (roadmap 9.2
// follow-up) — positioning/dragging a recorded-take region against a song's
// bar count. Percent-based (not pixel-based) since a region can start at an
// arbitrary offset, unlike the section timeline's flex-basis blocks.

/** A bar position → percent of the full timeline width (0..100). */
export function barToPercent(bar: number, totalBars: number): number {
  if (totalBars <= 0) return 0
  return Math.max(0, Math.min(100, (bar / totalBars) * 100))
}

/** A region's left offset + width, as percentages of the full timeline. */
export function regionRect(startBar: number, bars: number, loopCount: number,
                           totalBars: number): { leftPct: number; widthPct: number } {
  const leftPct = barToPercent(startBar, totalBars)
  const widthPct = barToPercent(startBar + bars * Math.max(1, loopCount), totalBars) - leftPct
  return { leftPct, widthPct: Math.max(0, widthPct) }
}

/** A horizontal drag delta (px) → whole bars, given the timeline's px-per-bar
 *  (rowWidthPx / totalBars). Regions are always bar-aligned. */
export function pxDeltaToBars(deltaPx: number, pxPerBar: number): number {
  if (pxPerBar <= 0) return 0
  return Math.round(deltaPx / pxPerBar)
}

/** Clamp a candidate new start bar so the region's full (looped) span never
 *  runs past the end of the song — the client-side mirror of the backend's
 *  400 bound, for a live drag preview that never overshoots. */
export function clampNewStartBar(newStartBar: number, bars: number, loopCount: number,
                                 totalBars: number): number {
  const span = bars * Math.max(1, loopCount)
  const maxStart = Math.max(0, totalBars - span)
  return Math.max(0, Math.min(maxStart, Math.round(newStartBar)))
}

/** Whether two regions' (start_bar, bars, loop_count) windows overlap — the
 *  same interval-overlap rule the backend uses to decide whether a
 *  newly-saved take should replace an existing region on the same part. */
export function regionsOverlap(
  a: { start_bar: number; bars: number; loop_count: number },
  b: { start_bar: number; bars: number; loop_count: number },
): boolean {
  const aEnd = a.start_bar + a.bars * Math.max(1, a.loop_count)
  const bEnd = b.start_bar + b.bars * Math.max(1, b.loop_count)
  return a.start_bar < bEnd && b.start_bar < aEnd
}
