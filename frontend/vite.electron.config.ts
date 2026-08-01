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
import { rmSync } from 'node:fs'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import electron from 'vite-plugin-electron/simple'

export default defineConfig({
  plugins: [
    // vite-plugin-electron's main/preload sub-builds default to emptyOutDir:false
    // (deliberately — they share dist-electron/ and build sequentially, so either
    // one clearing it would delete the other's output) but content-hashed chunk
    // filenames mean a changed hash leaves the OLD one behind as orphaned cruft.
    // Wiping the directory once, up front, before either sub-build writes anything,
    // gets a clean directory without that ordering hazard.
    { name: 'clean-dist-electron', buildStart: () => rmSync('dist-electron', { recursive: true, force: true }) },
    vue(),
    electron({
      main: {
        entry: 'electron/main.ts',
        vite: {
          build: {
            rolldownOptions: {
              // Resolved from packaged node_modules at runtime (electron-builder
              // ships production deps); bundling it breaks its dynamic requires.
              external: ['electron-updater'],
            },
          },
        },
      },
      preload: {
        input: 'electron/preload.ts',
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      '/exports': 'http://localhost:8000',
    },
  },
})
