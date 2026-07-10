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

export type RenderJobStatus = 'rendering' | 'done' | 'error'

export interface RenderJob {
  id: number
  label: string       // e.g. "drums — my_song" or "Song — my_song"
  filename: string    // with extension, e.g. "my_song.wav"
  status: RenderJobStatus
  progress: number    // 0-1, meaningful while status === 'rendering'
  error?: string
  blob?: Blob         // kept so "Save again" works after the tab that started it is gone
  createdAt: number
}

const MAX_JOBS = 30

// Module-scope so the job list and panel survive whichever component started the
// render being unmounted — switching mode tabs used to destroy SongResult/PartCard
// mid-export, along with the only refs tracking its progress. A render started
// through offlineRender() keeps running regardless (JS doesn't cancel a promise
// because its caller unmounted), but nothing was left to show it had — this queue
// is what's actually watching, independent of any one component's lifetime.
const jobs = ref<RenderJob[]>([])
const isOpen = ref(false)
let nextId = 1

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function useRenderQueue() {
  function startJob(label: string, filename: string): number {
    const id = nextId++
    jobs.value = [{ id, label, filename, status: 'rendering' as const, progress: 0, createdAt: Date.now() }, ...jobs.value].slice(0, MAX_JOBS)
    return id
  }
  function updateProgress(id: number, progress: number) {
    const job = jobs.value.find(j => j.id === id)
    if (job) job.progress = progress
  }
  function completeJob(id: number, blob: Blob) {
    const job = jobs.value.find(j => j.id === id)
    if (!job) return
    job.status = 'done'
    job.progress = 1
    job.blob = blob
    triggerDownload(blob, job.filename)
  }
  function failJob(id: number, error: string) {
    const job = jobs.value.find(j => j.id === id)
    if (!job) return
    job.status = 'error'
    job.error = error
  }
  function redownload(id: number) {
    const job = jobs.value.find(j => j.id === id)
    if (job?.blob) triggerDownload(job.blob, job.filename)
  }
  function removeJob(id: number) {
    jobs.value = jobs.value.filter(j => j.id !== id)
  }
  function clearFinished() {
    jobs.value = jobs.value.filter(j => j.status === 'rendering')
  }
  function open() { isOpen.value = true }
  function close() { isOpen.value = false }

  return { jobs, isOpen, startJob, updateProgress, completeJob, failJob, redownload, removeJob, clearFinished, open, close }
}
