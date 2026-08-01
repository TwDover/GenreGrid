/*
 * Roadmap 9.2 follow-up: the "+ section" control is now a type picker (was a
 * plain button that always inserted a verse). Confirms picking "bridge"
 * actually inserts a bridge, verified against the backend /songs listing.
 *
 * `gg` = { evaluate, screenshot, waitReady, raw(method,params), sleep }.
 */
export default async function (gg) {
  const log = (label, obj) => console.log('STEP', label, JSON.stringify(obj));

  const topSong = async () => gg.evaluate(`
    const r = await fetch('http://localhost:8000/songs').then(r => r.json());
    const s = r[0];
    return s ? { generation_id: s.generation_id, sections: s.sections.map(x => x.section_type) } : null;
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

  const build = await pollBackend('build', 180000, 3000, s => s && (!before || s.generation_id !== before.generation_id));
  if (!build.ok) throw new Error('no fresh song appeared within 180s');
  log('fresh-build', build.song);
  const genId = build.song.generation_id;
  await gg.sleep(1000);
  await gg.screenshot('/tmp/gg-insert-picker-1-built.png');

  // The picker: check its options, then select "bridge".
  const pickerInfo = await gg.evaluate(`
    const sel = document.querySelector('.sr-tl-insert');
    if (!sel) return { found: false };
    return { found: true, tag: sel.tagName, options: [...sel.options].map(o => o.value) };
  `);
  log('picker-info', pickerInfo);

  await gg.evaluate(`
    const sel = document.querySelector('.sr-tl-insert');
    sel.value = 'bridge';
    sel.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  `);
  await gg.screenshot('/tmp/gg-insert-picker-2-mid.png');

  const afterInsert = await pollBackend('insert-bridge', 150000, 3000,
    s => s && s.generation_id === genId && s.sections.length === build.song.sections.length + 1);
  log('after-insert', afterInsert);
  await gg.screenshot('/tmp/gg-insert-picker-3-done.png');

  const resetToPlaceholder = await gg.evaluate(`return document.querySelector('.sr-tl-insert')?.value;`);
  log('picker-reset', { value: resetToPlaceholder });

  console.log('DONE', JSON.stringify({
    insertedIsBridge: afterInsert.ok && afterInsert.song.sections[afterInsert.song.sections.length - 2] === 'bridge',
  }));
}
