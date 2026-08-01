/*
 * Roadmap 9.2 slice A live verification: build a song, then drag-reorder,
 * duplicate, and delete sections on the timeline, and confirm a lock blocks
 * a structural edit. Confirms via the BACKEND's /songs listing (not just DOM
 * state), since the app auto-restores the last-built song on launch — DOM
 * "blocks exist" alone can't tell a stale restored song from a fresh build.
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
                 sections: s.sections.map(x => x.section_type) } : null;
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

  // Give the DOM a moment to reflect the just-confirmed backend state, then screenshot.
  await gg.sleep(1000);
  await gg.screenshot('/tmp/gg-rearrange-1-built.png');
  const domCheck = await gg.evaluate(`
    return { blocks: document.querySelectorAll('.sr-tl-block').length, title: document.querySelector('.sr-title')?.textContent };
  `);
  log('dom-after-build', domCheck);

  // ── 1. Drag-reorder: drag block 0 onto block 2's right half ────────────────
  const initialSections = build.song.sections;
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
  const afterDrag = await pollBackend('drag', 90000, 3000,
    s => s && s.generation_id === genId && JSON.stringify(s.sections) !== JSON.stringify(initialSections));
  log('after-drag', afterDrag);
  await gg.screenshot('/tmp/gg-rearrange-2-dragged.png');

  // ── 2. Duplicate the first real section ─────────────────────────────────
  const sectionsBeforeDup = afterDrag.ok ? afterDrag.song.sections : initialSections;
  const barsBeforeDup = afterDrag.ok ? afterDrag.song.total_bars : build.song.total_bars;
  const dupClicked = await gg.evaluate(`
    const btns = [...document.querySelectorAll('.sr-tl-controls button')];
    const b = btns.find(b => b.textContent.trim() === '⧉');
    if (b) b.click();
    return !!b;
  `);
  const afterDup = await pollBackend('duplicate', 90000, 3000,
    s => s && s.generation_id === genId && s.sections.length === sectionsBeforeDup.length + 1);
  log('after-duplicate', { dupClicked, ...afterDup });
  await gg.screenshot('/tmp/gg-rearrange-3-duplicated.png');

  // ── 3. Delete a section ─────────────────────────────────────────────────
  const sectionsBeforeDel = afterDup.ok ? afterDup.song.sections : sectionsBeforeDup;
  const delClicked = await gg.evaluate(`
    const btns = [...document.querySelectorAll('.sr-tl-controls button')];
    const b = btns.find(b => b.textContent.trim() === '✕' && !b.disabled);
    if (b) b.click();
    return !!b;
  `);
  const afterDel = await pollBackend('delete', 90000, 3000,
    s => s && s.generation_id === genId && s.sections.length === sectionsBeforeDel.length - 1);
  log('after-delete', { delClicked, ...afterDel });
  await gg.screenshot('/tmp/gg-rearrange-4-deleted.png');

  // ── 4. Lock a part, confirm a structural edit is blocked (no backend call) ─
  const lockResult = await gg.evaluate(`
    const btn = document.querySelector('.lock-btn');
    if (!btn) return { found: false };
    btn.click();
    return { found: true, title: btn.title };
  `);
  await gg.sleep(400);
  const blockedUiState = await gg.evaluate(`
    return {
      errNote: document.querySelector('.sr-error')?.textContent || null,
      insertDisabled: document.querySelector('.sr-tl-insert')?.disabled ?? null,
      draggableAttr: document.querySelector('.sr-tl-block')?.getAttribute('draggable') ?? null,
    };
  `);
  log('locked-state', { lockResult, blockedUiState });
  await gg.screenshot('/tmp/gg-rearrange-5-locked.png');

  const sectionsBeforeBlockedAttempt = (await topSong()).sections;
  await gg.evaluate(`document.querySelector('.sr-tl-insert')?.click(); return true;`);
  await gg.sleep(4000);   // should be blocked client-side, so no backend round-trip to wait for
  const afterBlockedAttempt = await topSong();
  log('blocked-insert-attempt', {
    trulyBlocked: JSON.stringify(afterBlockedAttempt?.sections) === JSON.stringify(sectionsBeforeBlockedAttempt),
    sections: afterBlockedAttempt?.sections,
  });

  console.log('DONE');
}
