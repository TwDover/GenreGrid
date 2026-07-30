// Full edit path in the real shell: build a song, open a stem editor, insert a note
// via a synthetic drag on an empty grid row, and Save edits. Verifies the roadmap-5.1
// editor round-trips through the existing notes-changed → saveEdits → editPart path.
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

  // Open the first stem's ✎ editor.
  await gg.evaluate(`[...document.querySelectorAll('button')].find(b => b.textContent.trim() === '✎')?.click()`)
  await gg.sleep(800)

  // Insert a note: mousedown on an empty high row, drag right, release.
  const afterInsert = await gg.evaluate(`
    const cv = document.querySelector('.pre-canvas')
    if (!cv) return { err: 'no editor' }
    const r = cv.getBoundingClientRect()
    const x = r.left + 700, y = r.top + 60
    cv.dispatchEvent(new MouseEvent('mousedown', { clientX: x, clientY: y, bubbles: true }))
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: x + 90, clientY: y, bubbles: true }))
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: x + 90, clientY: y, bubbles: true }))
    const save = [...document.querySelectorAll('.pre-toolbar button')].find(b => b.textContent.trim() === 'Save edits')
    return { saveEnabled: save ? !save.disabled : null }
  `)
  await gg.screenshot('/tmp/gg-roll-inserted.png')

  // Click Save edits and let the backend rewrite the stem + rebuild song.mid.
  await click('Save edits', 2500)

  const afterSave = await gg.evaluate(`
    const save = [...document.querySelectorAll('.pre-toolbar button')].find(b => b.textContent.trim() === 'Save edits')
    return {
      editorStillOpen: !!document.querySelector('.pre-modal'),
      saveDisabledAfterSave: save ? save.disabled : null,   // back to clean → disabled
    }
  `)
  console.log(JSON.stringify({ afterInsert, afterSave }, null, 2))
}
