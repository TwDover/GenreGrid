/*
 * Live drive of the piano-roll INSERT feature (roadmap-v2 5.1 PR1).
 * Builds a fast song, then drags a new note onto the melody roll and confirms the
 * "Save edits" button appears (edit became dirty). Screenshots before + after.
 *
 * Run:  GG_SHOT=/tmp/insert.png node .claude/skills/run-genregrid/driver.mjs run \
 *         .claude/skills/run-genregrid/scenarios/insert-note.mjs
 */
export default async function (gg) {
  const shot = process.env.GG_SHOT || '/tmp/insert.png';

  // 1. Open Setup, choose the "song" mode card, pick the fast "Minimal" template.
  await gg.evaluate(`
    if (!document.querySelector('.sheet-top.open')) {
      [...document.querySelectorAll('button')].find(b => /Open Setup|Setup/.test(b.textContent))?.click();
    }
    return true;`);
  await gg.sleep(500);
  await gg.evaluate(`
    const cards = [...document.querySelectorAll('.mode-card')];
    // cards are ['loop','arrangement','song'] — song is always the 3rd. (Don't match
    // on text: the Arrangement card's description "A full arc" also contains "full".)
    (cards.find(c => /full song/i.test(c.textContent)) || cards[2])?.click();
    return cards.length;`);
  await gg.sleep(400);
  await gg.evaluate(`[...document.querySelectorAll('button')].find(b => /Minimal/i.test(b.textContent))?.click(); return true;`);
  await gg.sleep(200);

  // 2. Build the song.
  const built = await gg.evaluate(`
    const b = [...document.querySelectorAll('button')].find(x => /Build Full Song|Build Song/i.test(x.textContent));
    if (!b) return 'NO_BUILD_BUTTON';
    b.click(); return b.textContent.trim();`);
  console.log('build clicked:', built);

  // 3. Wait for the build to FINISH (button stops saying "Building song…"), then
  //    close the Setup drawer so the finished song's part cards are in front.
  let done = false;
  for (let i = 0; i < 120; i++) {
    const building = await gg.evaluate(`return [...document.querySelectorAll('button')].some(b => /Building song/i.test(b.textContent));`);
    if (!building && i > 1) { done = true; break; }
    await gg.sleep(1000);
  }
  console.log('build finished:', done);
  await gg.evaluate(`
    document.querySelector('.sheet-top button[title="Close"], .sheet-top .btn-icon')?.click();
    document.querySelector('.scrim.open')?.click();
    return true;`);
  await gg.sleep(800);

  // Now poll for editable rolls in the (front) song result.
  let canvases = 0;
  for (let i = 0; i < 30; i++) {
    canvases = await gg.evaluate(`
      return [...document.querySelectorAll('canvas.piano-roll.editable')]
        .filter(c => c.getBoundingClientRect().width > 0).length;`);
    if (canvases > 0) break;
    await gg.sleep(500);
  }
  console.log('editable canvases:', canvases);
  if (!canvases) { console.log('FAIL: no editable canvas appeared'); await gg.screenshot(shot); return; }

  await gg.screenshot(shot.replace(/\.png$/, '-before.png'));

  // 4. Drag a new note onto a melodic part's roll. Try melody, then chords, then any
  //    role-labeled (melodic) part; near the top of the roll = high pitch = empty space.
  const result = await gg.evaluate(`
    // Canvas-first: find each editable roll, read its owning part name via closest().
    const canv = [...document.querySelectorAll('canvas.piano-roll.editable')]
      .filter(c => c.getBoundingClientRect().width > 0)
      .map(c => ({ c, name: (c.closest('.part-track')?.querySelector('.part-name')?.textContent || '').toLowerCase() }));
    const pick = canv.find(x => /melody/.test(x.name)) || canv.find(x => /chord/.test(x.name))
      || canv.find(x => !/drum|kit/.test(x.name)) || canv[0];
    if (!pick) return { err: 'no editable canvas' };
    const canvas = pick.c;
    canvas.scrollIntoView({ block: 'center' });
    const r = canvas.getBoundingClientRect();
    const partName = pick.name;

    // Sweep candidate cells until one lands on EMPTY grid (→ "Save edits" appears).
    // Bias toward the left / upper region where a generated melody usually has gaps.
    const tick = () => new Promise(res => setTimeout(res, 80));   // let Vue flush the button
    const hasSave = () => [...document.querySelectorAll('button')].some(b => /Save edits/.test(b.textContent));
    const spots = [[0.12,0.30],[0.18,0.18],[0.15,0.50],[0.25,0.12],[0.08,0.60],
                   [0.30,0.35],[0.40,0.15],[0.55,0.10],[0.70,0.08]];
    for (const [xf, yf] of spots) {
      const y = r.top + r.height * yf;
      const x1 = r.left + r.width * xf, x2 = r.left + r.width * Math.min(0.95, xf + 0.14);
      canvas.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: x1, clientY: y }));
      window.dispatchEvent(new MouseEvent('mousemove', { clientX: x2, clientY: y }));
      window.dispatchEvent(new MouseEvent('mouseup',   { clientX: x2, clientY: y }));
      await tick();
      if (hasSave()) return { part: partName, spot: [xf, yf], saveEdits: true };
    }
    return { part: partName, saveEdits: hasSave() };
  `);
  console.log('insert result:', JSON.stringify(result));

  await gg.sleep(400);
  await gg.screenshot(shot);
  console.log('SCREENSHOT', shot);
}
