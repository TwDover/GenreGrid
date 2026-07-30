// Verify editor playback + loop region + audition wiring in the real shell.
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

  // Draw a loop region in the ruler, then press play.
  const before = await gg.evaluate(`
    const cv = document.querySelector('.pre-canvas'); if (!cv) return { err: 'no editor' }
    const r = cv.getBoundingClientRect()
    // Ruler drag (y a few px below the top of the canvas).
    const y = r.top + 6
    cv.dispatchEvent(new MouseEvent('mousedown', { clientX: r.left + 300, clientY: y, bubbles: true }))
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: r.left + 620, clientY: y, bubbles: true }))
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: r.left + 620, clientY: y, bubbles: true }))
    // Click a keyboard key (audition).
    cv.dispatchEvent(new MouseEvent('mousedown', { clientX: r.left + 20, clientY: r.top + 200, bubbles: true }))
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: r.left + 20, clientY: r.top + 200, bubbles: true }))
    return { transportSecs: (window).Tone ? null : 'no-tone' }
  `)
  await gg.sleep(300)
  // Press the transport ▶
  await gg.evaluate(`[...document.querySelectorAll('.pre-toolbar button')].find(b => b.textContent.trim() === '▶')?.click()`)
  await gg.sleep(1200)
  await gg.screenshot('/tmp/gg-roll-playing.png')
  const playing = await gg.evaluate(`
    const btn = [...document.querySelectorAll('.pre-toolbar button')].find(b => ['▶','■'].includes(b.textContent.trim()))
    return { transportLabel: btn ? btn.textContent.trim() : null, hasLoopClear: !!document.querySelector('.pre-loopclear') }
  `)
  console.log(JSON.stringify({ before, playing }, null, 2))
}
