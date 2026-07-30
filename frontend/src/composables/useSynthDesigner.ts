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

// Open/close state for the SynthDesigner panel (roadmap 6.6). A module-level singleton
// — the same shared-ref pattern as useCustomInstruments' panelOpen — so the transport
// button that opens it and the panel that renders it agree without prop-drilling. The
// working patch itself lives in the panel; nothing else needs it yet (part assignment
// is a later slice).
const open = ref(false)

export function useSynthDesigner() {
  return {
    open,
    openDesigner: () => { open.value = true },
    close: () => { open.value = false },
  }
}
