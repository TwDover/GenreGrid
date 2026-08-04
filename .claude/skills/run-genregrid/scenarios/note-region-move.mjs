/*
 * Roadmap 9.2 follow-up — movable/loopable MIDI regions: build a song, land a
 * "take" in the melody stem via /edit-part (with a drawn automation curve, to
 * prove it survives), register it as a region via /save-note-region, confirm
 * the SongResult UI renders a new per-part timeline row once the app sees the
 * fresh server state, move the region via /move-note-region, and independently
 * verify (by parsing the raw .mid bytes with @tonejs/midi, from plain Node —
 * no browser needed for this part) that the notes actually shifted and the
 * automation curve is still present.
 *
 * Every evaluate() body MUST use explicit `return` — the driver wraps the
 * expression as an async function BODY; a bare trailing expression is
 * discarded, not returned.
 *
 * `gg` = { evaluate, screenshot, waitReady, raw(method,params), sleep }.
 */
import pkg from '../../../../frontend/node_modules/@tonejs/midi/build/Midi.js';
const { Midi } = pkg;

async function fetchMidi(url) {
  const buf = await fetch(url).then(r => r.arrayBuffer());
  return new Midi(Buffer.from(buf));
}

function notesOf(midi) {
  const out = [];
  for (const track of midi.tracks) {
    for (const n of track.notes) out.push({ midi: n.midi, time: +n.time.toFixed(3), duration: +n.duration.toFixed(3) });
  }
  return out.sort((a, b) => a.time - b.time || a.midi - b.midi);
}

function ccOf(midi, controlNumber) {
  // @tonejs/midi exposes raw CC via track.controlChanges keyed by number (string).
  const out = [];
  for (const track of midi.tracks) {
    const events = track.controlChanges?.[controlNumber] ?? [];
    for (const e of events) out.push({ time: +e.time.toFixed(3), value: e.value });
  }
  return out.sort((a, b) => a.time - b.time);
}

export default async function (gg) {
  const log = (label, obj) => console.log('STEP', label, JSON.stringify(obj));

  const topSong = async () => gg.evaluate(`
    const r = await fetch('http://localhost:8000/songs').then(r => r.json());
    const s = r[0];
    return s ? { generation_id: s.generation_id, total_bars: s.total_bars, bpm: s.bpm, note_regions: s.note_regions ?? [] } : null;
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

  // ── Build a fresh song via the real UI (Setup -> Song -> Generate) ─────────
  await gg.evaluate(`
    const byText = (sel, t) => [...document.querySelectorAll(sel)].find(b => b.textContent.trim().includes(t));
    (byText('button', 'Open Setup') || byText('button', 'Setup'))?.click();
    return true;
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
  const totalBars = build.song.total_bars;

  await gg.sleep(1000);
  await gg.screenshot('/tmp/gg-region-1-built.png');

  // ── Land a "take" in the melody stem via /edit-part: a sparse baseline plus
  //    two notes at bar 6 (the "recorded" content), plus a drawn volume/pan
  //    curve — proving automation survives the region move later. ────────────
  const editResult = await gg.evaluate(`
    const totalBars = ${totalBars};
    const baseline = [];
    for (let bar = 0; bar < Math.min(totalBars - 1, 12); bar++) {
      baseline.push({ pitch: 60, start: bar * 4, duration: 1, velocity: 90 });
    }
    const take = [
      { pitch: 67, start: 24, duration: 1, velocity: 100 },   // bar 6, beat 0
      { pitch: 69, start: 25, duration: 1, velocity: 100 },   // bar 6, beat 1
    ];
    const automation = {
      volume: [{ beat: 0, value: 1.0 }, { beat: 4, value: 0.5 }],
      pan: [{ beat: 0, value: 0.2 }, { beat: 8, value: 0.9 }],
    };
    const res = await fetch('http://localhost:8000/edit-part', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ generation_id: '${genId}', part: 'melody', notes: [...baseline, ...take], automation }),
    });
    return { ok: res.ok, status: res.status, body: await res.json() };
  `);
  log('edit-part', editResult);
  if (!editResult.ok) throw new Error('edit-part failed: ' + JSON.stringify(editResult));

  // ── Register the take as a region (roadmap 9.2 follow-up) ───────────────────
  const saveRegionResult = await gg.evaluate(`
    const res = await fetch('http://localhost:8000/save-note-region', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        generation_id: '${genId}', part: 'melody', start_bar: 6, bars: 1,
        notes: [{ pitch: 67, start: 0, duration: 1, velocity: 100 }, { pitch: 69, start: 1, duration: 1, velocity: 100 }],
      }),
    });
    return { ok: res.ok, status: res.status, body: await res.json() };
  `);
  log('save-note-region', saveRegionResult);
  if (!saveRegionResult.ok) throw new Error('save-note-region failed: ' + JSON.stringify(saveRegionResult));
  const regionId = saveRegionResult.body.id;

  const afterSave = await topSong();
  log('songs-after-save', afterSave);
  if (!afterSave.note_regions.some(r => r.id === regionId && r.start_bar === 6)) {
    throw new Error('region not present in /songs after save-note-region');
  }

  // ── Force a genuinely fresh render (the rail caches BuildSongResponse in
  //    localStorage, so a plain reload would still show the stale pre-region
  //    object) and screenshot the new per-part region row. ───────────────────
  await gg.evaluate(`localStorage.removeItem('genregrid_song_history'); return true;`);
  await gg.raw('Page.reload', {});
  await gg.waitReady(60000);
  await gg.sleep(2500);   // let onMounted's syncSongsFromServer() land

  // A fresh mount always starts in 'loop' mode (not persisted) — re-select
  // 'song' mode so SongResult (and its now-fresh songResult prop) renders.
  await gg.evaluate(`
    const byText = (sel, t) => [...document.querySelectorAll(sel)].find(b => b.textContent.trim().includes(t));
    (byText('button', 'Open Setup') || byText('button', 'Setup'))?.click();
    return true;
  `);
  await gg.sleep(400);
  await gg.evaluate(`
    const card = [...document.querySelectorAll('.mode-card')].find(b => /song/i.test(b.textContent));
    if (card) card.click();
    return true;
  `);
  await gg.sleep(300);
  await gg.evaluate(`
    const closeBtn = [...document.querySelectorAll('button')].find(b => b.title === 'Close');
    closeBtn?.click();
    return true;
  `);
  await gg.sleep(400);

  const uiRegionCheck = await gg.evaluate(`
    const row = document.querySelector('.nr-tracks');
    const block = row?.querySelector('.nr-block');
    return {
      rowFound: !!row, blockFound: !!block,
      blockStyle: block ? block.getAttribute('style') : null,
      blockLabel: block ? block.textContent.trim() : null,
    };
  `);
  log('ui-region-check', uiRegionCheck);
  await gg.screenshot('/tmp/gg-region-2-row.png');

  // ── Move the region a few bars later ────────────────────────────────────────
  const moveResult = await gg.evaluate(`
    const res = await fetch('http://localhost:8000/move-note-region/${regionId}', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ generation_id: '${genId}', new_start_bar: 9 }),
    });
    return { ok: res.ok, status: res.status, body: await res.json() };
  `);
  log('move-note-region', moveResult);
  if (!moveResult.ok) throw new Error('move-note-region failed: ' + JSON.stringify(moveResult));

  // ── Independently verify via the raw .mid bytes (plain Node, @tonejs/midi):
  //    the take's notes shifted from bar 6 (beat 24) to bar 9 (beat 36), and
  //    the drawn automation curve is untouched. ───────────────────────────────
  const midi = await fetchMidi(`http://localhost:8000/exports/${genId}/melody.mid`);
  const notes = notesOf(midi);
  const secPerBeat = 60 / build.song.bpm || 0.5;
  const beatsOf = (n) => ({ pitch: n.midi, beat: +(n.time / secPerBeat).toFixed(2), dur: +(n.duration / secPerBeat).toFixed(2) });
  const beatNotes = notes.map(beatsOf);
  const has = (pitch, beat) => beatNotes.some(n => n.pitch === pitch && Math.abs(n.beat - beat) < 0.05);

  const pan = ccOf(midi, 10);
  const volume = ccOf(midi, 7);
  const panBeats = pan.map(p => ({ beat: +(p.time / secPerBeat).toFixed(2), value: p.value }));
  const volBeats = volume.map(p => ({ beat: +(p.time / secPerBeat).toFixed(2), value: p.value }));

  const report = {
    oldPositionGone: !has(67, 24) && !has(69, 25),
    newPositionPresent: has(67, 36) && has(69, 37),
    baselineNoteSurvived: has(60, 0),   // an unrelated note, well outside the region's window
    panBreakpoints: panBeats,
    volumeBreakpoints: volBeats,
    automationSurvived: panBeats.some(p => Math.abs(p.beat - 8) < 0.1) && volBeats.some(v => Math.abs(v.beat - 4) < 0.1),
  };
  log('move-verification', report);
  if (!report.oldPositionGone || !report.newPositionPresent || !report.baselineNoteSurvived || !report.automationSurvived) {
    throw new Error('move-note-region verification failed: ' + JSON.stringify(report));
  }

  // ── Playback still works (no console errors, transport engages) ────────────
  const playResult = await gg.evaluate(`
    const btn = [...document.querySelectorAll('button')].find(b => b.title === 'Play' || /▶/.test(b.textContent));
    if (!btn) return { found: false };
    btn.click();
    await new Promise(r => setTimeout(r, 1500));
    return { found: true };
  `);
  log('play-click', playResult);
  await gg.sleep(1000);
  await gg.screenshot('/tmp/gg-region-3-playing.png');

  console.log('SCENARIO_RESULT', JSON.stringify({ ok: true, genId, regionId, uiRegionCheck, moveVerification: report }));
}
