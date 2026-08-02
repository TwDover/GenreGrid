export default async function (gg) {
  await gg.sleep(800);
  const beforeErrors = [];
  await gg.evaluate(`window.__ggErrors = []; window.addEventListener('error', e => window.__ggErrors.push(String(e.error || e.message)));`);

  const opened = await gg.evaluate(`
    const btn = [...document.querySelectorAll('button')].find(b => b.title === 'Design a drum kit');
    if (!btn) return 'button not found';
    btn.click();
    return 'clicked';
  `);
  await gg.sleep(500);
  await gg.screenshot('/tmp/gg-drum-designer-open.png');

  const modalPresent = await gg.evaluate(`return !!document.querySelector('[aria-label="Drum designer"]')`);

  const padClicked = await gg.evaluate(`
    const pads = [...document.querySelectorAll('.dd-pad')];
    const kick = pads.find(b => b.textContent.trim() === 'Kick');
    if (!kick) return 'kick pad not found, pads=' + pads.map(p=>p.textContent).join(',');
    kick.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    return 'kick pad clicked';
  `);
  await gg.sleep(700);
  await gg.screenshot('/tmp/gg-drum-designer-after-kick.png');

  const errors = await gg.evaluate(`return window.__ggErrors`);

  console.log(JSON.stringify({ opened, modalPresent, padClicked, errors }, null, 2));
}
