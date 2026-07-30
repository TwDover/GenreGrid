// Verify roadmap-5.1 steps 3–4 in the real shell: marquee multi-select + velocity lane.
export default async function (gg) {
  const click = async (text, sleep = 400) => {
    await gg.evaluate(
      `[...document.querySelectorAll('button')].find(b => b.textContent.trim().includes(${JSON.stringify(text)}))?.click()`,
    )
    await gg.sleep(sleep)
  }

  await click('Open Setup', 700)
  await click('Song', 500)
  await click('Build Full Song', 6000)
  await gg.evaluate(`[...document.querySelectorAll('button')].find(b => b.textContent.trim() === '✎')?.click()`)
  await gg.sleep(800)

  // Switch to Select and marquee-drag a box over part of the grid.
  await click('Select', 300)
  const marquee = await gg.evaluate(`
    const cv = document.querySelector('.pre-canvas'); if (!cv) return { err: 'no editor' }
    const r = cv.getBoundingClientRect()
    const x0 = r.left + 250, y0 = r.top + 120, x1 = r.left + 620, y1 = r.top + 360
    cv.dispatchEvent(new MouseEvent('mousedown', { clientX: x0, clientY: y0, bubbles: true }))
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: x1, clientY: y1, bubbles: true }))
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: x1, clientY: y1, bubbles: true }))
    return true
  `)
  await gg.sleep(300)
  await gg.screenshot('/tmp/gg-roll-marquee.png')
  const selChip = await gg.evaluate(`document.querySelector('.pre-selcount')?.textContent?.trim() || null`)

  // Drag a velocity bar near the far left of the lane down to a low value.
  const veloResult = await gg.evaluate(`
    const cv = document.querySelector('.pre-canvas'); const r = cv.getBoundingClientRect()
    // Lane is the bottom ~68px above the ~12px scrollbar.
    const laneY = r.bottom - 12 - 55, x = r.left + 240
    cv.dispatchEvent(new MouseEvent('mousedown', { clientX: x, clientY: laneY, bubbles: true }))
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: x, clientY: r.bottom - 12 - 6, bubbles: true }))
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: x, clientY: r.bottom - 12 - 6, bubbles: true }))
    const save = [...document.querySelectorAll('.pre-toolbar button')].find(b => b.textContent.trim() === 'Save edits')
    return { saveEnabled: save ? !save.disabled : null }
  `)
  await gg.sleep(200)
  await gg.screenshot('/tmp/gg-roll-velocity.png')

  console.log(JSON.stringify({ marquee, selChip, veloResult }, null, 2))
}
