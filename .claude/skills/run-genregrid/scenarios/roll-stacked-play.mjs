// Regression: stack two notes on the same pitch/time in the editor, then play.
// Before the fix this threw Tone's "Start time must be strictly greater…". Now it plays.
export default async function (gg) {
  const errs = []
  const click = async (text, sleep = 400) => {
    await gg.evaluate(`[...document.querySelectorAll('button')].find(b => b.textContent.trim().includes(${JSON.stringify(text)}))?.click()`)
    await gg.sleep(sleep)
  }
  await click('Open Setup', 700)
  await click('Song', 500)
  await click('Build Full Song', 6000)
  await gg.evaluate(`[...document.querySelectorAll('button')].find(b => b.textContent.trim() === '✎')?.click()`)
  await gg.sleep(900)

  // Draw two notes at the SAME cell (same pitch + time) — the case that used to crash.
  await gg.evaluate(`
    window.__pperr = []
    window.addEventListener('error', e => window.__pperr.push(String(e.message || e.error)))
    const cv = document.querySelector('.pre-canvas'); const r = cv.getBoundingClientRect()
    const x = r.left + 360, y = r.top + 300
    const clickCell = () => {
      cv.dispatchEvent(new MouseEvent('mousedown', { clientX: x, clientY: y, bubbles: true }))
      window.dispatchEvent(new MouseEvent('mouseup', { clientX: x, clientY: y, bubbles: true }))
    }
    clickCell(); clickCell()   // two notes stacked on the same grid cell
  `)
  await gg.sleep(300)
  await gg.evaluate(`[...document.querySelectorAll('.pre-toolbar button')].find(b => b.textContent.trim() === '▶')?.click()`)
  await gg.sleep(1500)
  const out = await gg.evaluate(`{
    const btn = [...document.querySelectorAll('.pre-toolbar button')].find(b => ['▶','■'].includes(b.textContent.trim()))
    return { transport: btn ? btn.textContent.trim() : null, errors: window.__pperr || [] }
  }`)
  console.log(JSON.stringify(out, null, 2))
}
