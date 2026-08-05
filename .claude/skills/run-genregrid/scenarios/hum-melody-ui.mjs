/*
 * Roadmap 8.2 UI check: switch to Full Song mode, open the Advanced details
 * section, and confirm the new "…or hum/whistle it" field renders alongside
 * the existing melody/groove import rows. Real mic capture can't be driven
 * headlessly, so this only verifies the DOM + a click on "● Rec" doesn't throw
 * (a permission-denied error in this environment is expected and fine).
 *
 * `gg` = { evaluate, screenshot, waitReady, raw(method,params), sleep }.
 */
export default async function (gg) {
  await gg.evaluate(`
    const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim().endsWith('Setup'));
    if (b) b.click();
    return !!b;
  `);
  await gg.sleep(400);

  const afterSetupClick = await gg.evaluate(`
    const sheet = document.querySelector('.sheet-top');
    return { className: sheet ? sheet.className : null };
  `);
  console.log('AFTER_SETUP_CLICK', JSON.stringify(afterSetupClick));

  const switched = await gg.evaluate(`
    const byTitle = (t) => [...document.querySelectorAll('.mc-title')].find(s => s.textContent.trim() === t);
    const el = byTitle('Full Song');
    if (el) { el.closest('button').click(); return true; }
    return false;
  `);
  await gg.sleep(400);

  const opened = await gg.evaluate(`
    const form = document.querySelector('.song-form');
    if (!form) return false;
    const summary = [...form.querySelectorAll('summary')].find(s => s.textContent.includes('Advanced'));
    if (summary) { summary.closest('details').open = true; return true; }
    return false;
  `);
  await gg.sleep(300);

  const before = await gg.evaluate(`
    const form = document.querySelector('.song-form');
    const fields = form ? [...form.querySelectorAll('.field label')].map(l => l.textContent.trim().slice(0, 80)) : [];
    const recBtn = form ? [...form.querySelectorAll('.melody-row button')].find(b => b.textContent.includes('Rec')) : null;
    return { hasSongForm: !!form, fields, hasRecBtn: !!recBtn, recBtnText: recBtn ? recBtn.textContent.trim() : null };
  `);

  await gg.evaluate(`
    const label = [...document.querySelectorAll('.field label')].find(l => l.textContent.includes('hum/whistle'));
    if (label) label.scrollIntoView({ block: 'center' });
    return !!label;
  `);
  await gg.sleep(300);

  const drawerState = await gg.evaluate(`
    const sheet = document.querySelector('.sheet-top');
    if (!sheet) return { found: false };
    const rect = sheet.getBoundingClientRect();
    return { found: true, className: sheet.className, rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height } };
  `);
  console.log('DRAWER_STATE', JSON.stringify(drawerState));

  await gg.screenshot(process.env.GG_SHOT || '/tmp/hum-ui.png');

  const clickResult = await gg.evaluate(`
    try {
      const form = document.querySelector('.song-form');
      const recBtn = form ? [...form.querySelectorAll('.melody-row button')].find(b => b.textContent.includes('Rec')) : null;
      if (!recBtn) return { clicked: false };
      recBtn.click();
      return { clicked: true };
    } catch (e) {
      return { clicked: false, error: String(e) };
    }
  `);
  await gg.sleep(800);

  await gg.sleep(1500);   // let a couple seconds of (silent, headless) mic input accumulate

  const stopResult = await gg.evaluate(`
    const form = document.querySelector('.song-form');
    const stopBtn = form ? [...form.querySelectorAll('.melody-row button')].find(b => b.textContent.includes('Stop')) : null;
    if (!stopBtn) return { clicked: false };
    stopBtn.click();
    return { clicked: true };
  `);
  await gg.sleep(1000);   // decode + pitch-detect is synchronous JS but give the mic stream time to close

  const after = await gg.evaluate(`
    const errEl = document.querySelector('.hum-error');
    const capturedEl = document.querySelector('.hum-captured');
    const buildBtn = document.querySelector('.sb-generate-btn');
    return {
      errorText: errEl ? errEl.textContent.trim() : null,
      capturedText: capturedEl ? capturedEl.textContent.trim() : null,
      buildBtnText: buildBtn ? buildBtn.textContent.trim() : null,
    };
  `);
  await gg.screenshot((process.env.GG_SHOT || '/tmp/hum-ui.png').replace(/\.png$/, '-after-stop.png'));

  console.log('SCENARIO', JSON.stringify({ switched, opened, before, clickResult, stopResult, after }, null, 2));
}
