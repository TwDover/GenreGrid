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
import type { StyleInfo } from '../types/midi'

// Module-scope shared catalog (same pattern as useToasts/useErrorLog): HomePage
// populates it once from /styles; deep components (PartCard etc.) that only
// hold a styleId can resolve instrument labels without prop-drilling the list.
const catalog = ref<Map<string, StyleInfo>>(new Map())

export function setStyleCatalog(styles: StyleInfo[]): void {
  catalog.value = new Map(styles.map(s => [s.id, s]))
}

/** Instrument display name for a part in a style ("Alto Sax"), or null when
 *  the style is unknown / the part isn't bound — callers fall back to the
 *  part role name. */
export function instrumentLabel(styleId: string | undefined, part: string): string | null {
  if (!styleId) return null
  return catalog.value.get(styleId)?.instruments?.[part] ?? null
}

/** Playback voice id for a part in a style ("melody_lead", "electric_piano_1"),
 *  or null when unknown — callers fall back to legacy style-based voice logic. */
export function voiceFor(styleId: string | undefined, part: string): string | null {
  if (!styleId) return null
  return catalog.value.get(styleId)?.voices?.[part] ?? null
}

export function useStyleCatalog() {
  return { catalog, setStyleCatalog, instrumentLabel, voiceFor }
}
