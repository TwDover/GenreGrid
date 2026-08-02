// Live drive of the Volume/Pan automation lane (roadmap 9.3). Builds a song, opens a
// stem's full-screen editor, switches the bottom lane to Volume then Pan and draws a
// point in each via a synthetic drag, saves, and verifies the baked CC7/CC10 events are
// actually in the saved stem's bytes (not just that the UI looked right).
export default async function (gg) {
  const click = async (text, sleep = 400) => {
    await gg.evaluate(
      `[...document.querySelectorAll('button')].find(b => b.textContent.trim().includes(${JSON.stringify(text)}))?.click()`,
    )
    await gg.sleep(sleep)
  }
  const tick = `await new Promise(r => setTimeout(r, 80))`

  await click('Open Setup', 700)
  await click('Song', 500)
  await click('Build Full Song', 6000)

  // Open the melody stem's ✎ editor (falls back to the first stem's if melody isn't found).
  await gg.evaluate(`
    const rows = [...document.querySelectorAll('.part-track')]
    const pick = rows.find(r => /melody/i.test(r.querySelector('.part-name')?.textContent || '')) || rows[0]
    const btn = [...(pick ? pick.querySelectorAll('button') : [])].find(b => b.textContent.trim() === '✎')
      || [...document.querySelectorAll('button')].find(b => b.textContent.trim() === '✎')
    btn?.click()
    ${tick}
  `)
  await gg.sleep(700)

  // Draw a Volume point, then a Pan point, in the bottom lane. A single mousedown+up
  // (no move) already inserts a breakpoint — onPointerDown handles the insert itself.
  const drawn = await gg.evaluate(`
    const cv = document.querySelector('.pre-canvas')
    if (!cv) return { err: 'no editor' }
    const r = cv.getBoundingClientRect()
    const clickAt = (x, y) => {
      cv.dispatchEvent(new MouseEvent('mousedown', { clientX: x, clientY: y, bubbles: true }))
      window.dispatchEvent(new MouseEvent('mouseup', { clientX: x, clientY: y, bubbles: true }))
    }
    const clickBtn = (label) => [...document.querySelectorAll('.pre-toolbar button')]
      .find(b => b.textContent.trim() === label)?.click()

    clickBtn('Volume')
    ${tick}
    clickAt(r.left + r.width * 0.3, r.bottom - 40)   // upper half of the lane -> high volume
    ${tick}
    clickBtn('Pan')
    ${tick}
    clickAt(r.left + r.width * 0.6, r.bottom - 20)   // lower half -> panned one way
    ${tick}

    const save = [...document.querySelectorAll('.pre-toolbar button')].find(b => b.textContent.trim() === 'Save edits')
    return { saveEnabled: save ? !save.disabled : null, rect: { w: r.width, h: r.height } }
  `)
  console.log('drawn:', JSON.stringify(drawn))
  await gg.screenshot('/tmp/gg-automation-lane-drawn.png')

  // Capture the melody stem's own URL for free: PartCard's save path re-fetches it
  // (cacheTempFile) right after a successful save, so a thin fetch wrapper installed
  // just before clicking Save records it without any guesswork about the DOM.
  await gg.evaluate(`
    window.__ggFetchedMidUrls = []
    if (!window.__ggOrigFetch) window.__ggOrigFetch = window.fetch.bind(window)
    window.fetch = (...args) => {
      const u = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '')
      if (/\\.mid(\\?|$)/.test(u)) window.__ggFetchedMidUrls.push(u)
      return window.__ggOrigFetch(...args)
    }
  `)

  await click('Save edits', 2500)

  const afterSave = await gg.evaluate(`
    const save = [...document.querySelectorAll('.pre-toolbar button')].find(b => b.textContent.trim() === 'Save edits')
    return {
      saveDisabledAfterSave: save ? save.disabled : null,
      fetchedMidUrls: window.__ggFetchedMidUrls || [],
    }
  `)
  console.log('afterSave:', JSON.stringify(afterSave))

  // Independently verify the bake: fetch the melody stem and scan raw bytes for a
  // control_change (0xB_) message with controller 7 (volume) or 10 (pan). This 3-byte
  // pattern is contiguous regardless of the preceding variable-length delta time, so a
  // raw byte scan reliably proves the CC actually landed (not just that the UI looked right).
  const midUrl = (afterSave.fetchedMidUrls || []).find(u => /melody\.mid/.test(u)) || (afterSave.fetchedMidUrls || [])[0]
  let bytesCheck = { err: 'no melody.mid fetch observed' }
  if (midUrl) {
    bytesCheck = await gg.evaluate(`
      const buf = new Uint8Array(await (await fetch(${JSON.stringify(midUrl)})).arrayBuffer())
      let hasCC7 = false, hasCC10 = false
      for (let i = 0; i < buf.length - 2; i++) {
        if ((buf[i] & 0xf0) === 0xb0) {
          if (buf[i + 1] === 7) hasCC7 = true
          if (buf[i + 1] === 10) hasCC10 = true
        }
      }
      return { url: ${JSON.stringify(midUrl)}, byteLength: buf.length, hasCC7, hasCC10 }
    `)
  }
  console.log('bytesCheck:', JSON.stringify(bytesCheck))
  console.log(JSON.stringify({ drawn, afterSave, bytesCheck }, null, 2))
}
