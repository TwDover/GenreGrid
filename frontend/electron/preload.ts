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
})
