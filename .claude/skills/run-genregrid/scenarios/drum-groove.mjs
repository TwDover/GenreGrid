export default async function (gg) {
  await gg.sleep(800);
  await gg.evaluate(`window.__ggErrors = []; window.addEventListener('error', e => window.__ggErrors.push(String(e.error || e.message)));`);

  await gg.evaluate(`[...document.querySelectorAll('button')].find(b => b.title === 'Design a drum kit')?.click()`);
  await gg.sleep(400);

  // Nudge a few sliders (buzz mix, humanize) so their values are non-default, and confirm.
  const setSlider = async (label, value) => {
    await gg.evaluate(`
      const row = [...document.querySelectorAll('.dd-row')].find(r => r.querySelector('.dd-label')?.textContent.trim() === '${label}');
      if (!row) return 'row not found: ${label}';
      const input = row.querySelector('input[type=range]');
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(input, '${value}');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    `);
    await gg.sleep(150);
    return gg.evaluate(`
      const row = [...document.querySelectorAll('.dd-row')].find(r => r.querySelector('.dd-label')?.textContent.trim() === '${label}');
      return 'readback: ' + row.querySelector('.dd-val').textContent;
    `);
  };
  const buzzResult = await setSlider('Buzz mix', '0.7');
  const humanizeResult = await setSlider('Humanize', '0.6');

  // Start the loop.
  const loopStart = await gg.evaluate(`
    const btn = [...document.querySelectorAll('.dd-loop-btn')][0];
    if (!btn) return 'loop button not found';
    btn.click();
    return 'clicked: ' + btn.textContent.trim();
  `);
  await gg.sleep(1500);
  await gg.screenshot('/tmp/gg-groove-playing.png');

  // Step to next preset while looping.
  await gg.evaluate(`
    const btn = [...document.querySelectorAll('.dd-mini')].find(b => b.title === 'Next');
    btn?.click();
  `);
  await gg.sleep(300);
  const browseResult = await gg.evaluate(`return 'preset now: ' + document.querySelector('.dd-preset').value`);
  await gg.sleep(1000);

  // Hit a pad while looping (should layer, not crash).
  const padResult = await gg.evaluate(`
    const pads = [...document.querySelectorAll('.dd-pad')];
    const kick = pads.find(b => b.textContent.trim() === 'Kick');
    if (!kick) return 'kick pad not found';
    kick.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    return 'kick pad hit while looping';
  `);
  await gg.sleep(500);
  await gg.screenshot('/tmp/gg-groove-with-pad.png');

  // Stop the loop.
  const loopStop = await gg.evaluate(`
    const btn = [...document.querySelectorAll('.dd-loop-btn')][0];
    btn.click();
    return 'clicked: ' + btn.textContent.trim();
  `);
  await gg.sleep(300);

  const errors = await gg.evaluate(`return window.__ggErrors`);
  console.log(JSON.stringify({ buzzResult, humanizeResult, loopStart, browseResult, padResult, loopStop, errors }, null, 2));
}
