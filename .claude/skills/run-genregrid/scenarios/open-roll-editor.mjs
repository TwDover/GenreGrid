// Build a short song, open a stem's full piano-roll editor, and screenshot it.
// Verifies the roadmap-5.1 zoomable modal editor renders in the real Electron shell.
export default async function (gg) {
  const click = async (text, sleep = 400) => {
    await gg.evaluate(
      `[...document.querySelectorAll('button')].find(b => b.textContent.trim().includes(${JSON.stringify(text)}))?.click()`,
    )
    await gg.sleep(sleep)
  }

  // Open Setup, switch to the Song tab if present, and build a full song.
  await click('Open Setup', 700)
  // The song form lives behind a "Song" mode/tab in the setup drawer.
  await click('Song', 500)
  await click('Build Full Song', 6000)
  await gg.screenshot('/tmp/gg-song-built.png')

  // Find the first editable stem's ✎ button and open the editor.
  const opened = await gg.evaluate(`
    const btn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === '✎')
    if (btn) { btn.click(); return true }
    return false
  `)
  await gg.sleep(800)
  await gg.screenshot('/tmp/gg-roll-editor.png')

  // Report what the editor exposes (toolbar + canvas presence).
  const state = await gg.evaluate(`
    const modal = document.querySelector('.pre-modal')
    return {
      editorOpen: !!modal,
      openedViaButton: ${opened},
      hasCanvas: !!document.querySelector('.pre-canvas'),
      toolbarButtons: [...document.querySelectorAll('.pre-toolbar button')].map(b => b.textContent.trim()),
      title: document.querySelector('.pre-title')?.textContent?.trim() || null,
      snapOptions: [...document.querySelectorAll('.pre-snap option')].map(o => o.textContent.trim()),
    }
  `)
  console.log(JSON.stringify(state, null, 2))
}
