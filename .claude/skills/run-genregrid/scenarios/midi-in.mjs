// Enables MIDI-in and screenshots the transport so the part/device pickers show.
export default async function (gg) {
  await gg.evaluate(`[...document.querySelectorAll('button')].find(b => /midi in/i.test(b.textContent||''))?.click();`)
  await gg.sleep(1000)
  await gg.evaluate(`
    const sel = document.querySelector('.tb-midi-sel');   // set part to melody explicitly
    if (sel) { sel.value = 'melody'; sel.dispatchEvent(new Event('change')); }
  `)
  await gg.sleep(400)
  await gg.screenshot('/tmp/gg-midi-on.png')
  const s = await gg.evaluate(`return {
    on: !!document.querySelector('.tb-midi-btn.is-on'),
    selects: document.querySelectorAll('.tb-midi-sel').length,
  };`)
  console.log('MIDI-IN:', JSON.stringify(s))
}
