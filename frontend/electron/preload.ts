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
import { contextBridge, ipcRenderer } from 'electron'

// Fetch the backend port synchronously before the renderer scripts run
const apiPort = ipcRenderer.sendSync('get-api-port') as number

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  apiPort,

  // Write MIDI bytes to a temp file on disk; returns the absolute file path
  saveTempFile: (filename: string, data: number[]): Promise<string> =>
    ipcRenderer.invoke('save-temp-file', { filename, data }),

  // Trigger a native OS drag from the given file path (DAWs can receive this).
  // sendSync keeps this in the same event frame as the dragstart gesture.
  startDrag: (filePath: string): void => {
    ipcRenderer.sendSync('start-drag', filePath)
  },

  // Manual update check. Resolves to { status, version, latest?, message? }:
  // 'downloading' (update found, downloading in background), 'uptodate',
  // 'unsupported' (unsigned macOS), 'dev' (not packaged), or 'error'.
  checkForUpdates: (): Promise<{ status: string; version: string; latest?: string; message?: string }> =>
    ipcRenderer.invoke('check-for-updates'),
})
