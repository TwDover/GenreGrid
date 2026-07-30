// Verify loop start/end flags + clarified Zoom buttons in the editor, and the
// Shortcuts modal's new entries. Screenshots the editor toolbar + loop flags.
export default async function (gg) {
  const click = async (text, sleep = 400) => {
    await gg.evaluate(`[...document.querySelectorAll('button')].find(b => b.textContent.trim().includes(${JSON.stringify(text)}))?.click()`)
    await gg.sleep(sleep)
  }
  await click('Open Setup', 700)
  await click('Song', 500)
  await click('Build Full Song', 6000)
  await gg.evaluate(`[...document.querySelectorAll('button')].find(b => b.textContent.trim() === '✎')?.click()`)
  await gg.sleep(900)

  // Drag out a loop region, then drag the END flag to move just that edge.
  const res = await gg.evaluate(`
    const cv = document.querySelector('.pre-canvas'); if (!cv) return { err: 'no editor' }
    const r = cv.getBoundingClientRect(); const y = r.top + 6
    const drag = (x0, x1) => {
      cv.dispatchEvent(new MouseEvent('mousedown', { clientX: r.left + x0, clientY: y, bubbles: true }))
      window.dispatchEvent(new MouseEvent('mousemove', { clientX: r.left + x1, clientY: y, bubbles: true }))
      window.dispatchEvent(new MouseEvent('mouseup', { clientX: r.left + x1, clientY: y, bubbles: true }))
    }
    drag(260, 560)                    // set region
    return { hasLoopClear: !!document.querySelector('.pre-loopclear'),
             zoomButtons: [...document.querySelectorAll('.pre-toolbar .pre-axis')].map(s => s.textContent.trim()),
             glabels: [...document.querySelectorAll('.pre-glabel')].map(s => s.textContent.trim()) }
  `)
  await gg.sleep(300)
  await gg.screenshot('/tmp/gg-loop-flags.png')
  console.log(JSON.stringify(res, null, 2))
}
