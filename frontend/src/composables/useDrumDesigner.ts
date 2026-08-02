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

// Open/close state for the DrumDesigner panel — the drum-side analog of
// useSynthDesigner.ts. Same module-level singleton pattern so the transport
// button that opens it and the panel that renders it agree without prop-drilling.
const open = ref(false)

export function useDrumDesigner() {
  return {
    open,
    openDesigner: () => { open.value = true },
    close: () => { open.value = false },
  }
}
