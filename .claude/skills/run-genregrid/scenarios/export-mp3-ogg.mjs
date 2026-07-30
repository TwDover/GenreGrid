// Roadmap 5.2 in the real shell: generate a loop, then export the mix as MP3 and
// as OGG from the Export row's format toggle. Captures the Blob the download would
// write (by hooking URL.createObjectURL) and checks its MIME + magic bytes —
// proving the real Chromium offline render + the lazy-loaded WASM encoder produce
// valid files in the packaged Electron runtime, not just under vitest. Uses the
// fast loop path (a few bars) rather than a full song so it finishes promptly.
export default async function (gg) {
  const click = async (text, sleep = 400) => {
    await gg.evaluate(
      `[...document.querySelectorAll('button')].find(b => b.textContent.trim().includes(${JSON.stringify(text)}))?.click()`,
    )
    await gg.sleep(sleep)
  }

  // Intercept the download so we can inspect the encoded bytes headlessly.
  await gg.evaluate(`
    window.__exported = null
    const orig = URL.createObjectURL.bind(URL)
    URL.createObjectURL = (blob) => {
      if (blob instanceof Blob) {
        blob.arrayBuffer().then(ab => {
          window.__exported = { type: blob.type, size: blob.size, magic: [...new Uint8Array(ab.slice(0, 4))] }
        })
      }
      return orig(blob)
    }
  `)

  await click('Open Setup', 700)
  await click('Generate', 5000)   // Loop is the default mode — a short, fast render

  // Export the mix in a given format: pick the fmt toggle, hit ⏬ Mix, name + Save.
  const exportAs = async (fmt) => {
    await gg.evaluate(`window.__exported = null`)
    await gg.evaluate(
      `[...document.querySelectorAll('.fmt-btn')].find(b => b.textContent.trim() === ${JSON.stringify(fmt)})?.click()`,
    )
    await gg.sleep(200)
    await gg.evaluate(`[...document.querySelectorAll('.btn-audio')].find(b => b.textContent.includes('Mix'))?.click()`)
    await gg.sleep(500)                                   // filename modal opens
    await gg.evaluate(`document.querySelector('.dnp-save')?.click()`)
    // First MP3/OGG export lazy-loads ~0.6 MB of WASM, then renders + encodes.
    for (let i = 0; i < 90; i++) {
      const e = await gg.evaluate(`return window.__exported`)
      if (e) return e
      await gg.sleep(500)
    }
    return null
  }

  const mp3 = await exportAs('MP3')
  const ogg = await exportAs('OGG')

  // 0xFF 0xFB… = MPEG audio frame sync; 'OggS' = 0x4F 0x67 0x67 0x53.
  const ok = {
    mp3Valid: mp3?.type === 'audio/mpeg' && mp3?.magic?.[0] === 0xff && (mp3?.magic?.[1] & 0xe0) === 0xe0 && mp3.size > 0,
    oggValid: ogg?.type === 'audio/ogg' && JSON.stringify(ogg?.magic) === JSON.stringify([0x4f, 0x67, 0x67, 0x53]) && ogg.size > 0,
  }
  await gg.screenshot('/tmp/gg-export-formats.png')
  console.log(JSON.stringify({ mp3, ogg, ok }, null, 2))
}
