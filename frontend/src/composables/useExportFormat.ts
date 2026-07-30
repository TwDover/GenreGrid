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
// The chosen audio-export format (WAV / MP3 / OGG), shared app-wide so the loop
// workspace, the song result, and per-part stem downloads all honour one choice
// — pick MP3 once and every ↓ audio button writes MP3 until you change it.
import { ref } from 'vue'
import type { AudioFormat } from '../utils/audioEncoder'

const audioFormat = ref<AudioFormat>('wav')

export function useExportFormat() {
  return { audioFormat }
}
