/*
 * Roadmap 9.2 resize-UI gap: build a song, drag a section block's right-edge
 * resize handle wider, and confirm the section's bar count actually changes
 * on the backend (not just a DOM flex-basis change) — plus that a plain click
 * on a block still seeks, and drag-reorder still works (no regression from
 * the new mousedown handler on the block).
 *
 * Every evaluate() body MUST use explicit `return` — the driver wraps the
 * expression as an async function BODY; a bare trailing expression is
 * discarded, not returned.
 *
 * `gg` = { evaluate, screenshot, waitReady, raw(method,params), sleep }.
 */
export default async function (gg) {
  const log = (label, obj) => console.log('STEP', label, JSON.stringify(obj));

  const topSong = async () => gg.evaluate(`
    const r = await fetch('http://localhost:8000/songs').then(r => r.json());
    const s = r[0];
    return s ? { generation_id: s.generation_id, total_bars: s.total_bars,
                 sections: s.sections.map(x => ({ type: x.section_type, bars: x.bars })) } : null;
  `);

  async function pollBackend(label, maxMs, stepMs, pred) {
    const start = Date.now();
    let s = await topSong();
    while (Date.now() - start < maxMs) {
      if (pred(s)) return { ok: true, elapsedMs: Date.now() - start, song: s };
      await gg.sleep(stepMs);
      s = await topSong();
    }
    console.log('  TIMEOUT', label, JSON.stringify(s));
    return { ok: false, elapsedMs: Date.now() - start, song: s };
  }

  const before = await topSong();
  log('songs-before', before);

  // ── Build a fresh song ───────────────────────────────────────────────────
  await gg.evaluate(`
    const byText = (sel, t) => [...document.querySelectorAll(sel)].find(b => b.textContent.trim().includes(t));
    (byText('button', 'Open Setup') || byText('button', 'Setup'))?.click();
  `);
  await gg.sleep(500);
  await gg.evaluate(`
    const card = [...document.querySelectorAll('.mode-card')].find(b => /song/i.test(b.textContent));
    if (card) card.click();
    return true;
  `);
  await gg.sleep(300);
  const genClicked = await gg.evaluate(`
    const b = document.querySelector('.sb-generate-btn');
    if (b && !b.disabled) { b.click(); return true; }
    return { exists: !!b, disabled: b?.disabled };
  `);
  log('generate-clicked', genClicked);

  const build = await pollBackend('build', 180000, 3000,
    s => s && (!before || s.generation_id !== before.generation_id));
  if (!build.ok) throw new Error('no fresh song appeared in /songs within 180s');
  log('fresh-build', build.song);
  const genId = build.song.generation_id;

  await gg.sleep(1000);
  await gg.screenshot('/tmp/gg-resize-1-built.png');

  // ── 1. Hover the right edge of block 0 — handle should be findable and the
  //      block itself must carry an ew-resize affordance region. ─────────────
  const handleCheck = await gg.evaluate(`
    const block = document.querySelectorAll('.sr-tl-block')[0];
    const handle = block?.querySelector('.sr-tl-resize-handle');
    return { blockFound: !!block, handleFound: !!handle,
             cursor: handle ? getComputedStyle(handle).cursor : null };
  `);
  log('handle-check', handleCheck);

  // ── 2. Drag the handle of block 0 rightward by real screen pixels ──────────
  const initialSections = build.song.sections;
  const dragResult = await gg.evaluate(`
    const block = document.querySelectorAll('.sr-tl-block')[0];
    const handle = block.querySelector('.sr-tl-resize-handle');
    const rect = block.getBoundingClientRect();
    const startX = rect.right - 2;
    const pxPerBar = rect.width / ${initialSections[0].bars};
    const targetDeltaBars = 4;
    const endX = startX + pxPerBar * targetDeltaBars;
    const fire = (el, type, clientX) => el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, clientX, clientY: rect.top + rect.height / 2 }));
    fire(handle, 'mousedown', startX);
    fire(window, 'mousemove', (startX + endX) / 2);
    fire(window, 'mousemove', endX);
    fire(window, 'mouseup', endX);
    return { rectWidth: rect.width, pxPerBar, startX, endX };
  `);
  log('drag-fired', dragResult);

  const afterResize = await pollBackend('resize', 90000, 3000,
    s => s && s.generation_id === genId && s.sections[0].bars !== initialSections[0].bars);
  log('after-resize', afterResize);
  await gg.screenshot('/tmp/gg-resize-2-resized.png');

  // ── 3. A plain click on a DIFFERENT block still seeks (no regression) ──────
  const clickCheck = await gg.evaluate(`
    const blocks = [...document.querySelectorAll('.sr-tl-block')];
    const before = document.querySelector('.sr-play-btn')?.classList.contains('playing');
    blocks[1]?.click();
    return { before, blockCount: blocks.length };
  `);
  await gg.sleep(800);
  const clickAfter = await gg.evaluate(`
    return { playing: document.querySelector('.sr-play-btn')?.classList.contains('playing') };
  `);
  log('click-seek-check', { ...clickCheck, ...clickAfter });

  // ── 4. Drag-reorder still works after the resize handler landed ────────────
  const sectionsBeforeDrag = (await topSong()).sections;
  await gg.evaluate(`
    const blocks = [...document.querySelectorAll('.sr-tl-block')];
    const src = blocks[0], dst = blocks[2];
    const dt = new DataTransfer();
    const rect = dst.getBoundingClientRect();
    const fire = (el, type, extra) => el.dispatchEvent(new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: dt, ...extra }));
    fire(src, 'dragstart');
    fire(dst, 'dragover', { clientX: rect.right - 2 });
    fire(dst, 'drop', { clientX: rect.right - 2 });
    fire(src, 'dragend');
    return true;
  `);
  const afterDrag = await pollBackend('drag-after-resize', 90000, 3000,
    s => s && s.generation_id === genId && JSON.stringify(s.sections) !== JSON.stringify(sectionsBeforeDrag));
  log('drag-still-works', afterDrag);
  await gg.screenshot('/tmp/gg-resize-3-drag-still-works.png');

  console.log('DONE');
}
