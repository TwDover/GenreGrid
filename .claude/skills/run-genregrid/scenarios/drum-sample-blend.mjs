export default async function (gg) {
  await gg.sleep(800);
  await gg.evaluate(`window.__ggErrors = []; window.addEventListener('error', e => window.__ggErrors.push(String(e.error || e.message)));`);

  // ── Step 1: open Instruments panel, upload a fake "kick.wav" as a drum kit ──
  await gg.evaluate(`[...document.querySelectorAll('button')].find(b => b.title?.includes('custom instruments'))?.click()`);
  await gg.sleep(400);

  await gg.evaluate(`
    const nameInput = [...document.querySelectorAll('input[type=text]')].find(i => i.placeholder === 'Instrument name');
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(nameInput, 'Test Kick Kit');
    nameInput.dispatchEvent(new Event('input', { bubbles: true }));
    const kindSelect = [...document.querySelectorAll('select')].find(s => [...s.options].some(o => o.value === 'drums'));
    const setSel = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
    setSel.call(kindSelect, 'drums');
    kindSelect.dispatchEvent(new Event('change', { bubbles: true }));
  `);

  // Find the file input's DOM nodeId via CDP and set files on it directly (real
  // filesystem path, so this exercises the true Electron file-read path).
  const doc = await gg.raw('DOM.getDocument', { depth: -1, pierce: true });
  const findFileInput = await gg.raw('DOM.querySelector', {
    nodeId: doc.root.nodeId,
    selector: 'input[type=file][accept*="audio"]',
  });
  await gg.raw('DOM.setFileInputFiles', {
    files: ['/tmp/gg-drum-sample-test/kick.wav'],
    nodeId: findFileInput.nodeId,
  });
  await gg.sleep(300);

  const pickedResult = await gg.evaluate(`return document.querySelector('.ip-picked')?.textContent ?? 'no picked-count shown'`);

  const importResult = await gg.evaluate(`
    const btn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Add instrument');
    if (!btn || btn.disabled) return 'import button not found/disabled';
    btn.click();
    return 'clicked import';
  `);
  await gg.sleep(1500);
  const afterImport = await gg.evaluate(`return document.querySelector('.ip-lib h3')?.textContent ?? 'lib heading not found'`);
  await gg.screenshot('/tmp/gg-instruments-uploaded.png');

  // Close instruments panel.
  await gg.evaluate(`[...document.querySelectorAll('.ip-x')].find(b => b.title === 'Close')?.click()`);
  await gg.sleep(300);

  // ── Step 2: open Drum Designer, select the uploaded kit as sample base ──
  await gg.evaluate(`[...document.querySelectorAll('button')].find(b => b.title === 'Design a drum kit')?.click()`);
  await gg.sleep(400);

  const sampleBaseResult = await gg.evaluate(`
    const rows = [...document.querySelectorAll('.dd-row')];
    const row = rows.find(r => r.querySelector('.dd-label')?.textContent.trim() === 'Kit');
    if (!row) return 'Kit row not found';
    const select = row.querySelector('select');
    const opt = [...select.options].find(o => o.textContent.includes('Test Kick Kit'));
    if (!opt) return 'kit not in dropdown, options=' + [...select.options].map(o=>o.textContent).join(',');
    const setSel = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
    setSel.call(select, opt.value);
    select.dispatchEvent(new Event('change', { bubbles: true }));
    return 'selected: ' + opt.textContent;
  `);
  await gg.sleep(300);
  await gg.screenshot('/tmp/gg-designer-sample-base.png');

  // Set blend to 1.0 (pure sample) and hit the kick pad.
  await gg.evaluate(`
    const rows = [...document.querySelectorAll('.dd-row')];
    const row = rows.find(r => r.querySelector('.dd-label')?.textContent.trim() === 'Blend');
    const input = row?.querySelector('input[type=range]');
    if (input) {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(input, '1');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
  `);
  await gg.sleep(300);
  const blendReadback = await gg.evaluate(`
    const rows = [...document.querySelectorAll('.dd-row')];
    const row = rows.find(r => r.querySelector('.dd-label')?.textContent.trim() === 'Blend');
    return row ? row.querySelector('.dd-val').textContent : 'blend row not found';
  `);

  const padResult = await gg.evaluate(`
    const pads = [...document.querySelectorAll('.dd-pad')];
    const kick = pads.find(b => b.textContent.trim() === 'Kick');
    if (!kick) return 'kick pad not found';
    kick.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    return 'kick pad hit';
  `);
  await gg.sleep(1000);   // let the async materialize+rebuild resolve
  const padResult2 = await gg.evaluate(`
    const kick = [...document.querySelectorAll('.dd-pad')].find(b => b.textContent.trim() === 'Kick');
    kick.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    return 'second kick pad hit (should use materialized sample by now)';
  `);
  await gg.sleep(500);

  const errors = await gg.evaluate(`return window.__ggErrors`);
  console.log(JSON.stringify({
    pickedResult, importResult, afterImport, sampleBaseResult, blendReadback, padResult, padResult2, errors,
  }, null, 2));
}
