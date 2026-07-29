/*
 * Live drive of the piano-roll RESIZE feature (roadmap-v2 5.1 PR2).
 * Builds a song, inserts a note of known length on the melody roll, then grabs that
 * note's right edge (= the insert's end x) and drags it further right to lengthen it.
 * Screenshots before + after so the note is visibly longer.
 *
 * Run: GG_SHOT=/tmp/resize.png node .claude/skills/run-genregrid/driver.mjs run \
 *        .claude/skills/run-genregrid/scenarios/resize-note.mjs
 */
export default async function (gg) {
  const shot = process.env.GG_SHOT || '/tmp/resize.png';

  // 1. Open Setup → Full Song → Minimal → Build.  (Same flow as insert-note.mjs.)
  await gg.evaluate(`if (!document.querySelector('.sheet-top.open')) [...document.querySelectorAll('button')].find(b=>/Open Setup|Setup/.test(b.textContent))?.click(); return true;`);
  await gg.sleep(500);
  await gg.evaluate(`const c=[...document.querySelectorAll('.mode-card')]; (c.find(x=>/full song/i.test(x.textContent))||c[2])?.click(); return true;`);
  await gg.sleep(400);
  await gg.evaluate(`[...document.querySelectorAll('button')].find(b=>/Minimal/i.test(b.textContent))?.click(); return true;`);
  await gg.sleep(200);
  await gg.evaluate(`[...document.querySelectorAll('button')].find(b=>/Build Full Song|Build Song/i.test(b.textContent))?.click(); return true;`);

  // 2. Wait for build, close the drawer.
  for (let i = 0; i < 120; i++) {
    const building = await gg.evaluate(`return [...document.querySelectorAll('button')].some(b=>/Building song/i.test(b.textContent));`);
    if (!building && i > 1) break;
    await gg.sleep(1000);
  }
  await gg.evaluate(`document.querySelector('.sheet-top button[title="Close"], .sheet-top .btn-icon')?.click(); document.querySelector('.scrim.open')?.click(); return true;`);
  await gg.sleep(800);

  let canvases = 0;
  for (let i = 0; i < 30; i++) {
    canvases = await gg.evaluate(`return [...document.querySelectorAll('canvas.piano-roll.editable')].filter(c=>c.getBoundingClientRect().width>0).length;`);
    if (canvases > 0) break;
    await gg.sleep(500);
  }
  if (!canvases) { console.log('FAIL: no editable canvas'); await gg.screenshot(shot); return; }

  // 3. Insert a note of known length on the melody roll, then RESIZE its right edge.
  const result = await gg.evaluate(`
    const tick = () => new Promise(r => setTimeout(r, 90));
    const canv = [...document.querySelectorAll('canvas.piano-roll.editable')]
      .filter(c => c.getBoundingClientRect().width > 0)
      .map(c => ({ c, name: (c.closest('.part-track')?.querySelector('.part-name')?.textContent||'').toLowerCase() }));
    const pick = canv.find(x => /melody/.test(x.name)) || canv.find(x => /chord/.test(x.name)) || canv[0];
    const canvas = pick.c; canvas.scrollIntoView({ block: 'center' });
    const drag = (type, x, y, onWin) => (onWin ? window : canvas).dispatchEvent(new MouseEvent(type, { bubbles: true, clientX: x, clientY: y }));

    // Insert a moderate-length note in the empty left region; its END x becomes the edge.
    const r = canvas.getBoundingClientRect();
    const y = r.top + r.height * 0.30;
    const startX = r.left + r.width * 0.12;
    const endX   = r.left + r.width * 0.26;
    drag('mousedown', startX, y, false);
    drag('mousemove', endX, y, true);
    drag('mouseup',   endX, y, true);
    await tick();
    window.__ggShot = 'inserted';
    return { part: pick.name, endXFrac: 0.26 };
  `);
  console.log('inserted:', JSON.stringify(result));
  await gg.screenshot(shot.replace(/\.png$/, '-before.png'));

  const resized = await gg.evaluate(`
    const tick = () => new Promise(r => setTimeout(r, 90));
    const canv = [...document.querySelectorAll('canvas.piano-roll.editable')]
      .filter(c => c.getBoundingClientRect().width > 0)
      .map(c => ({ c, name: (c.closest('.part-track')?.querySelector('.part-name')?.textContent||'').toLowerCase() }));
    const pick = canv.find(x => /melody/.test(x.name)) || canv.find(x => /chord/.test(x.name)) || canv[0];
    const canvas = pick.c;
    const r = canvas.getBoundingClientRect();
    const y = r.top + r.height * 0.30;
    const edgeX = r.left + r.width * 0.26;   // the inserted note's right edge
    const toX   = r.left + r.width * 0.58;   // drag it much further right
    canvas.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: edgeX, clientY: y }));
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: toX, clientY: y }));
    window.dispatchEvent(new MouseEvent('mouseup',   { clientX: toX, clientY: y }));
    await tick();
    const saveEdits = [...document.querySelectorAll('button')].some(b => /Save edits/.test(b.textContent));
    return { saveEdits };
  `);
  console.log('resized:', JSON.stringify(resized));
  await gg.sleep(300);
  await gg.screenshot(shot);
  console.log('SCREENSHOT', shot);
}
