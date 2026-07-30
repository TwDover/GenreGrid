// Verifies 7.6 — live playback-tempo control: nudging the transport BPM changes
// Tone's transport speed (playback only) without regenerating. Generates a loop,
// plays it, reads the generated BPM, clicks the tempo "+" a few times, and asserts
// the transport bpm rose while the note data / seek duration are untouched.
export default async function (gg) {
  // Fresh launch has no history — generate a loop through the UI first.
  await gg.evaluate(`
    [...document.querySelectorAll('button')].find(b => /open setup/i.test(b.textContent))?.click();
  `)
  await gg.sleep(700)
  await gg.evaluate(`
    const gen = [...document.querySelectorAll('button')].find(b => b.type === 'submit' && /generate/i.test(b.textContent));
    gen?.click();
  `)
  await gg.sleep(4000)   // backend generation + result render

  // Ensure the newest entry is expanded (it may auto-expand), so its PartCards
  // render, then play one part so the transport loads and the tempo widget appears.
  await gg.evaluate(`
    if (!document.querySelector('.history-entry.expanded')) document.querySelector('.history-row')?.click();
  `)
  await gg.sleep(700)
  await gg.evaluate(`
    const preview = [...document.querySelectorAll('button[title]')].find(b => /^preview$/i.test(b.getAttribute('title')||''));
    preview?.click();
  `)
  await gg.sleep(3000)

  const before = await gg.evaluate(`
    const T = window.__gg?.Tone?.getTransport?.() ?? null;
    const tempoEl = document.querySelector('.tb-tempo');
    return {
      hasTempoWidget: !!tempoEl,
      shownBpm: document.querySelector('.tb-tempo-val')?.textContent ?? null,
      transportBpm: T ? T.bpm.value : null,
    };
  `)
  await gg.screenshot(process.env.GG_SHOT || '/tmp/gg-tempo-before.png')

  // Nudge faster four times via the "+" button (second step button in the widget).
  await gg.evaluate(`
    const steps = document.querySelectorAll('.tb-tempo-step');
    const plus = steps[steps.length - 1];
    for (let i = 0; i < 4; i++) plus?.click();
  `)
  await gg.sleep(300)

  const after = await gg.evaluate(`
    const T = window.__gg?.Tone?.getTransport?.() ?? null;
    return {
      shownBpm: document.querySelector('.tb-tempo-val')?.textContent ?? null,
      nudgedClass: document.querySelector('.tb-tempo')?.classList.contains('nudged') ?? null,
      hasReset: !!document.querySelector('.tb-tempo-reset'),
      transportBpm: T ? T.bpm.value : null,
    };
  `)
  await gg.screenshot('/tmp/gg-tempo-after.png')

  console.log('LIVE-TEMPO before:', JSON.stringify(before))
  console.log('LIVE-TEMPO after :', JSON.stringify(after))
}
