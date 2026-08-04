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
// A minimal in-memory mock of the OPFS handle interfaces (FileSystemDirectoryHandle
// / FileSystemFileHandle / writable streams) — jsdom has no real OPFS, and there's
// no existing OPFS test precedent in this codebase, so this stands in for a real
// browser's sandboxed filesystem. Implements just enough of the spec for
// opfsInstrumentStorage.ts's usage: getDirectoryHandle/getFileHandle (with
// {create}), removeEntry, entries() (a plain Map iterator works fine with
// `for await`, which falls back to the sync iterator protocol), getFile()
// (.text()/.arrayBuffer()), and createWritable() (.write()/.close()).
import { describe, it, expect, beforeEach } from 'vitest'
import {
  fileHandleForPath, readAllFiles, opfsInstrumentStorage,
  __resetOpfsInstrumentStorageForTests,
} from './opfsInstrumentStorage'
import type { CustomInstrument } from './customInstruments'

class MockFileHandle {
  readonly kind = 'file' as const
  private bytes = new Uint8Array()
  constructor(public name: string) {}
  async getFile() {
    const bytes = this.bytes
    return {
      async text() { return new TextDecoder().decode(bytes) },
      async arrayBuffer() { return bytes.slice().buffer },
    }
  }
  async createWritable() {
    let pending = new Uint8Array()
    return {
      write: async (data: BufferSource | string) => {
        if (typeof data === 'string') pending = new TextEncoder().encode(data)
        else if (data instanceof Uint8Array) pending = new Uint8Array(data)
        else pending = new Uint8Array(data as ArrayBuffer)
      },
      close: async () => { this.bytes = pending },
    }
  }
}

class MockDirHandle {
  readonly kind = 'directory' as const
  children = new Map<string, MockDirHandle | MockFileHandle>()
  constructor(public name: string) {}
  async getDirectoryHandle(name: string, opts?: { create?: boolean }): Promise<MockDirHandle> {
    let h = this.children.get(name)
    if (!h) {
      if (!opts?.create) throw new DOMException('not found', 'NotFoundError')
      h = new MockDirHandle(name)
      this.children.set(name, h)
    }
    if (!(h instanceof MockDirHandle)) throw new Error(`${name} is a file, not a directory`)
    return h
  }
  async getFileHandle(name: string, opts?: { create?: boolean }): Promise<MockFileHandle> {
    let h = this.children.get(name)
    if (!h) {
      if (!opts?.create) throw new DOMException('not found', 'NotFoundError')
      h = new MockFileHandle(name)
      this.children.set(name, h)
    }
    if (!(h instanceof MockFileHandle)) throw new Error(`${name} is a directory, not a file`)
    return h
  }
  async removeEntry(name: string, _opts?: { recursive?: boolean }): Promise<void> {
    if (!this.children.has(name)) throw new DOMException('not found', 'NotFoundError')
    this.children.delete(name)
  }
  entries() { return this.children.entries() }
}

function installMockOpfs(): MockDirHandle {
  const root = new MockDirHandle('root')
  Object.defineProperty(globalThis.navigator, 'storage', {
    configurable: true,
    value: { getDirectory: async () => root },
  })
  __resetOpfsInstrumentStorageForTests()
  return root
}

beforeEach(() => {
  installMockOpfs()
})

describe('fileHandleForPath', () => {
  it('creates intermediate directories for a nested path', async () => {
    const root = new MockDirHandle('root')
    const fh = await fileHandleForPath(root as unknown as FileSystemDirectoryHandle, 'hard/C4.mp3', true)
    expect(fh.name).toBe('C4.mp3')
    expect(root.children.get('hard')).toBeInstanceOf(MockDirHandle)
  })

  it('does not create directories when create=false and throws if missing', async () => {
    const root = new MockDirHandle('root')
    await expect(fileHandleForPath(root as unknown as FileSystemDirectoryHandle, 'missing/x.wav', false))
      .rejects.toThrow()
  })
})

describe('readAllFiles', () => {
  it('recursively collects nested files with their relative paths', async () => {
    const root = new MockDirHandle('root')
    const fh1 = await fileHandleForPath(root as unknown as FileSystemDirectoryHandle, 'a.wav', true)
    const w1 = await fh1.createWritable()
    await w1.write(new Uint8Array([1, 2, 3]))
    await w1.close()
    const fh2 = await fileHandleForPath(root as unknown as FileSystemDirectoryHandle, 'hard/b.wav', true)
    const w2 = await fh2.createWritable()
    await w2.write(new Uint8Array([4, 5]))
    await w2.close()

    const files = await readAllFiles(root as unknown as FileSystemDirectoryHandle)
    const byName = Object.fromEntries(files.map(f => [f.name, f.data]))
    expect(byName['a.wav']).toEqual([1, 2, 3])
    expect(byName['hard/b.wav']).toEqual([4, 5])
  })
})

const inst = (id: string, over: Partial<CustomInstrument> = {}): CustomInstrument => ({
  id, name: 'Test', kind: 'melodic', manifest: { layers: [] }, createdAt: 1, ...over,
})

describe('opfsInstrumentStorage — feature detection', () => {
  it('returns undefined when navigator.storage.getDirectory is unavailable', () => {
    Object.defineProperty(globalThis.navigator, 'storage', { configurable: true, value: undefined })
    expect(opfsInstrumentStorage()).toBeUndefined()
  })

  it('returns an api object when OPFS is available', () => {
    expect(opfsInstrumentStorage()).toBeTruthy()
  })
})

describe('opfsInstrumentStorage — list/save/read/remove', () => {
  it('starts with an empty library', async () => {
    const api = opfsInstrumentStorage()!
    expect(await api.list()).toEqual([])
  })

  it('saves an instrument with its audio files, then lists and reads it back', async () => {
    const api = opfsInstrumentStorage()!
    const i = inst('inst-1')
    await api.save(i, [
      { name: 'C4.mp3', data: [1, 2, 3] },
      { name: 'velocity/hard/C4.mp3', data: [4, 5] },
    ])

    const list = await api.list()
    expect(list).toHaveLength(1)
    expect(list[0]).toEqual(i)

    const files = await api.read('inst-1')
    const byName = Object.fromEntries(files.map(f => [f.name, f.data]))
    expect(byName['C4.mp3']).toEqual([1, 2, 3])
    expect(byName['velocity/hard/C4.mp3']).toEqual([4, 5])
  })

  it('updates the index in place without duplicating an entry (updateKitSlot-style resave)', async () => {
    const api = opfsInstrumentStorage()!
    await api.save(inst('inst-1', { name: 'First' }), [{ name: 'a.wav', data: [1] }])
    await api.save(inst('inst-1', { name: 'Renamed' }), [])   // metadata-only resave, no new files

    const list = await api.list()
    expect(list).toHaveLength(1)
    expect(list[0].name).toBe('Renamed')
    // The earlier file must still be there — a metadata-only save doesn't touch files.
    const files = await api.read('inst-1')
    expect(files.map(f => f.name)).toContain('a.wav')
  })

  it('keeps two instruments independent', async () => {
    const api = opfsInstrumentStorage()!
    await api.save(inst('a'), [{ name: 'x.wav', data: [9] }])
    await api.save(inst('b'), [{ name: 'y.wav', data: [8] }])

    expect((await api.list()).map(i => i.id).sort()).toEqual(['a', 'b'])
    expect((await api.read('a')).map(f => f.name)).toEqual(['x.wav'])
    expect((await api.read('b')).map(f => f.name)).toEqual(['y.wav'])
  })

  it('removes an instrument and its files, leaving others untouched', async () => {
    const api = opfsInstrumentStorage()!
    await api.save(inst('a'), [{ name: 'x.wav', data: [1] }])
    await api.save(inst('b'), [{ name: 'y.wav', data: [2] }])

    await api.remove('a')

    expect((await api.list()).map(i => i.id)).toEqual(['b'])
    expect(await api.read('a')).toEqual([])
    expect((await api.read('b')).map(f => f.name)).toEqual(['y.wav'])
  })

  it('removing a never-saved id is a harmless no-op', async () => {
    const api = opfsInstrumentStorage()!
    await expect(api.remove('nope')).resolves.toBeUndefined()
  })

  it('reading a never-saved id returns an empty file list', async () => {
    const api = opfsInstrumentStorage()!
    expect(await api.read('nope')).toEqual([])
  })
})
