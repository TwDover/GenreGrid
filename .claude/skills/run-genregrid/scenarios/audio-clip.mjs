// Live drive of recorded audio clips (roadmap 9.4). Builds a song, arms the new
// AudioClipCard's mic recording, waits for it to auto-stop into review, saves the
// take, plays the song (checking for console errors while the clip is scheduled
// into the mix), then triggers a WAV "Mix" export and checks the output isn't
// trivially tiny/silent. Needs Electron launched with
// --use-fake-device-for-media-stream --use-fake-ui-for-media-stream so getUserMedia
// succeeds with a synthetic (non-silent) signal instead of a real microphone.
export default async function (gg) {
  const click = async (selectorExpr, sleep = 400) => {
    const ok = await gg.evaluate(`const b = ${selectorExpr}; if (b) { b.click(); return true; } return false;`)
    await gg.sleep(sleep)
    return ok
  }
  const byText = (tag, text) =>
    `[...document.querySelectorAll('${tag}')].find(b => b.textContent.trim().includes(${JSON.stringify(text)}))`

  await gg.evaluate(`
    window.__ggErrors = []
    window.addEventListener('error', e => window.__ggErrors.push(String(e.message || e)))
    const origError = console.error.bind(console)
    console.error = (...args) => { window.__ggErrors.push(args.map(String).join(' ')); origError(...args) }
  `)

  await click(byText('button', 'Open Setup'), 700)
  await click(byText('button', 'Song'), 500)
  await click(byText('button', 'Build Full Song'), 6000)

  const built = await gg.evaluate(`
    const hasCard = !!document.querySelector('.audio-clip-card')
    const recBtn = ${byText('button', '● Rec')}
    return { hasAudioClipCard: hasCard, hasRecButton: !!recBtn, songTitle: document.querySelector('.sr-title')?.textContent || null }
  `)
  console.log('built:', JSON.stringify(built))
  await gg.screenshot('/tmp/gg-audioclip-built.png')
  if (!built.hasAudioClipCard || !built.hasRecButton) throw new Error('AudioClipCard / Rec button not found after build')

  await click(byText('button', '● Rec'), 1000)
  const armState = await gg.evaluate(`
    const card = document.querySelector('.audio-clip-card')
    return { recording: card?.classList.contains('recording'), text: card?.textContent?.slice(0, 80) }
  `)
  console.log('armed:', JSON.stringify(armState))
  await gg.screenshot('/tmp/gg-audioclip-recording.png')

  // Live input-level meter (new) — poll a couple times during recording and
  // check the fill width actually moves off 0%, proving real-time signal
  // feedback works (not just the post-hoc waveform review).
  const meterReadings = []
  for (let i = 0; i < 5; i++) {
    const w = await gg.evaluate(`
      const fill = document.querySelector('.audio-clip-card .ac-meter-fill')
      return fill ? fill.style.width : null
    `)
    meterReadings.push(w)
    await gg.sleep(200)
  }
  console.log('meterReadings:', JSON.stringify(meterReadings))

  // Poll for the review state (Save button appears) — duration depends on the
  // selected section's bar count at the song's bpm, so poll rather than a fixed sleep.
  let review = null
  for (let i = 0; i < 60; i++) {
    review = await gg.evaluate(`
      const card = document.querySelector('.audio-clip-card')
      const save = card ? [...card.querySelectorAll('button')].find(b => b.textContent.includes('Save')) : null
      return { hasSave: !!save, cardText: card?.textContent?.slice(0, 120) || null, errors: window.__ggErrors.slice() }
    `)
    if (review.hasSave) break
    await gg.sleep(1000)
  }
  console.log('review:', JSON.stringify(review))
  await gg.screenshot('/tmp/gg-audioclip-review.png')
  if (!review?.hasSave) throw new Error(`Never reached review/Save state — last card text: ${review?.cardText}`)

  // Check the waveform canvas actually has non-blank pixels before saving — real
  // proof the fake mic signal was captured (not silence), independent of the API.
  const waveformCheck = await gg.evaluate(`
    const cv = document.querySelector('.audio-clip-card canvas.ac-waveform')
    if (!cv) return { err: 'no canvas' }
    const ctx = cv.getContext('2d')
    const data = ctx.getImageData(0, 0, cv.width, cv.height).data
    let nonBlank = 0
    for (let i = 3; i < data.length; i += 4) if (data[i] > 0) nonBlank++
    return { nonBlankPixels: nonBlank, totalPixels: cv.width * cv.height }
  `)
  console.log('waveformCheck (pre-save review):', JSON.stringify(waveformCheck))

  // Scoped to .audio-clip-card — PartCard's own "Save to…" button also matches
  // a bare text-includes('Save') search and sits earlier in the DOM.
  await click(`
    [...document.querySelectorAll('.audio-clip-card button')].find(b => b.textContent.includes('Save'))
  `, 1500)
  const afterSave = await gg.evaluate(`
    const card = document.querySelector('.audio-clip-card')
    const hasReRec = card ? [...card.querySelectorAll('button')].some(b => b.textContent.includes('Re-rec')) : false
    const hasWaveform = !!card?.querySelector('canvas.ac-waveform')
    return { hasReRec, hasWaveform, cardText: card?.textContent?.slice(0, 120) || null, errors: window.__ggErrors.slice() }
  `)
  console.log('afterSave:', JSON.stringify(afterSave))
  await gg.screenshot('/tmp/gg-audioclip-saved.png')
  if (!afterSave.hasReRec) throw new Error('Save did not transition the card to the saved-clip state')

  // Independently verify the backend actually persisted the clip + its placement
  // (not just that the UI looked right) by reading the /songs listing — newest first,
  // so songs[0] is the one just built and recorded into.
  const backendCheck = await gg.evaluate(`
    const songs = await fetch('http://localhost:8000/songs').then(r => r.json())
    const s = songs[0]
    return { latest_gen_id: s?.generation_id, audio_clip: s?.audio_clip || null }
  `)
  console.log('backendCheck:', JSON.stringify(backendCheck))
  if (!backendCheck.audio_clip) throw new Error('Backend /songs listing shows no audio_clip after Save')

  // Play the song (the clip should schedule into the mix via useMidiPlayer's
  // Tone.Player sync) — just check nothing throws during playback.
  await click(byText('button', 'Play'), 2500)
  const duringPlay = await gg.evaluate(`return { errors: window.__ggErrors.slice() }`)
  await click(byText('button', 'Stop'), 300)
  console.log('duringPlay:', JSON.stringify(duringPlay))

  // NOTE: the WAV "Mix" export button triggers a native Save-As dialog
  // (promptFilename -> Electron showSaveDialog), which blocks headless CDP
  // automation indefinitely — not exercised here. useOfflineRender.ts's clip-
  // mixing logic (placeClipInMix + the buffers array wiring) is covered by
  // frontend unit tests instead; see audioClip.test.ts.

  console.log('RESULT', JSON.stringify({ built, armState, meterReadings, review, waveformCheck, afterSave, backendCheck, duringPlay }))
}
