// Toggles the standalone metronome and samples the destination meter to confirm
// periodic click peaks (no track loaded → clicks at the default tempo).
export default async function (gg) {
  await gg.evaluate(`await window.__gg.Tone.start();`)
  // Click the metronome ♩ button.
  await gg.evaluate(`[...document.querySelectorAll('button')].find(b => (b.textContent||'').trim()==='♩')?.click();`)
  await gg.sleep(300)
  const r = await gg.evaluate(`
    const T = window.__gg.Tone;
    const m = new T.Meter();
    T.getDestination().connect(m);
    return await new Promise(res => {
      const vals = []; let n = 0;
      const id = setInterval(() => {
        let v = m.getValue(); if (Array.isArray(v)) v = Math.max(v[0], v[1]);
        vals.push(isFinite(v) ? Math.round(v) : -99);
        if (++n >= 40) { clearInterval(id); res(vals); }
      }, 50);   // ~2s of samples
    });
  `)
  const peaks = r.filter(v => v > -45).length
  console.log('METRO-CHECK peaks(>-45dB):', peaks, 'of', r.length, 'samples')
  console.log('METRO-CHECK meter:', JSON.stringify(r))
  await gg.screenshot('/tmp/gg-metro.png')
}
