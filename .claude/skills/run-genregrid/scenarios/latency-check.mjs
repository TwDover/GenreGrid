// Confirms the low-latency buffer is active and playback produces continuous audio.
export default async function (gg) {
  await gg.evaluate(`[...document.querySelectorAll('button')].find(b => /open setup/i.test(b.textContent))?.click();`)
  await gg.sleep(600)
  await gg.evaluate(`[...document.querySelectorAll('button')].find(b => b.type==='submit' && /generate/i.test(b.textContent))?.click();`)
  await gg.sleep(4500)
  await gg.evaluate(`if(!document.querySelector('.history-entry.expanded')) document.querySelector('.history-row')?.click();`)
  await gg.sleep(700)
  // Play the combined/first part.
  await gg.evaluate(`[...document.querySelectorAll('button[title]')].find(b=>/^preview$/i.test(b.getAttribute('title')||''))?.click();`)
  await gg.sleep(1500)
  const r = await gg.evaluate(`
    const c = window.__gg.ctx();
    const m = window.__gg.meterMaster();
    return new Promise(res => {
      const vals = [];
      let n = 0;
      const id = setInterval(() => {
        let v = m.getValue(); if (Array.isArray(v)) v = Math.max(v[0], v[1]);
        vals.push(isFinite(v) ? Math.round(v) : -99);
        if (++n >= 8) { clearInterval(id); res({ baseLatencyMs: Math.round((c.baseLatency||0)*1000), meterDb: vals }); }
      }, 200);
    });
  `)
  console.log('LATENCY-CHECK:', JSON.stringify(r))
}
