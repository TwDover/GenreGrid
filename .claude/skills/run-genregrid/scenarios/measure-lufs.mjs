// Roadmap 6.2 — measure integrated LUFS (ITU-R BS.1770-4, gated) for every style's
// rendered mix, in the real Electron shell (the offline render pipeline — samplers,
// synths, per-style FX, the limiter — only exists in the renderer, not in Python).
//
// For each style: generate an 8-bar loop straight against the backend API (fast, no
// UI clicking), then call offlineRenderRaw() directly via the temporarily-extended
// window.__gg hook (see main.ts) — this bypasses the UI's Save-As flow entirely,
// which (since 7.1b) opens a real native OS dialog that would hang headless CDP.
//
// One evaluate() call PER STYLE (not one giant call for all 35) — gives visible
// per-style progress in the Node console and means one stuck style can't silently
// swallow the whole sweep behind a single opaque hang.
const DSP = `
  function biquad(x, b, a) {
    const y = new Float32Array(x.length)
    let x1 = 0, x2 = 0, y1 = 0, y2 = 0
    for (let n = 0; n < x.length; n++) {
      const xn = x[n]
      const yn = b[0]*xn + b[1]*x1 + b[2]*x2 - a[1]*y1 - a[2]*y2
      y[n] = yn
      x2 = x1; x1 = xn; y2 = y1; y1 = yn
    }
    return y
  }
  // ITU-R BS.1770-4 Table 1/2 coefficients, defined at 48kHz — resample to 48k first.
  function kWeight(x, fs) {
    let s = x, sr = fs
    if (sr !== 48000) {
      const ratio = 48000 / sr
      const n = Math.round(s.length * ratio)
      const y = new Float32Array(n)
      for (let i = 0; i < n; i++) {
        const p = i / ratio, i0 = Math.floor(p), i1 = Math.min(i0 + 1, s.length - 1)
        const f = p - i0
        y[i] = s[i0] * (1 - f) + s[i1] * f
      }
      s = y; sr = 48000
    }
    const stage1 = biquad(s, [1.53512485958697, -2.69169618940638, 1.19839281085285], [1, -1.69065929318241, 0.73248077421585])
    return biquad(stage1, [1.0, -2.0, 1.0], [1, -1.99004745483398, 0.99007225036621])
  }
  function integratedLufs(L, R, fs) {
    const kL = kWeight(L, fs), kR = kWeight(R, fs)
    const sr = 48000, blockSize = Math.round(0.4 * sr), hop = Math.round(0.1 * sr)
    const toLufs = z => -0.691 + 10 * Math.log10(z)
    const blocks = []
    for (let start = 0; start + blockSize <= kL.length; start += hop) {
      let sumL = 0, sumR = 0
      for (let i = 0; i < blockSize; i++) { const l = kL[start+i], r = kR[start+i]; sumL += l*l; sumR += r*r }
      blocks.push((sumL + sumR) / blockSize)
    }
    const absGated = blocks.filter(z => z > 0 && toLufs(z) > -70)
    if (!absGated.length) return -Infinity
    const meanAbs = absGated.reduce((a,b) => a+b, 0) / absGated.length
    const relThreshold = toLufs(meanAbs) - 10
    const relGated = absGated.filter(z => toLufs(z) > relThreshold)
    const meanRel = (relGated.length ? relGated : absGated).reduce((a,b) => a+b, 0) / (relGated.length || absGated.length)
    return toLufs(meanRel)
  }
`

function withTimeout(promise, ms, label) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error(`timed out after ${ms}ms: ${label}`)), ms)),
  ])
}

export default async function (gg) {
  // Self-test: a full-scale 997Hz sine, L===R (dual-mono stereo — doubles the power
  // sum vs a true mono file), should measure close to 0 LUFS. Sanity-checks the
  // filter+gating math once before trusting the per-style numbers below.
  const selfTest = await gg.evaluate(`
    ${DSP}
    const sr = 48000, dur = 2
    const sine = new Float32Array(sr * dur)
    for (let i = 0; i < sine.length; i++) sine[i] = Math.sin(2 * Math.PI * 997 * i / sr)
    return integratedLufs(sine, sine, sr)
  `)
  console.log(`selfTest (997Hz full-scale dual-mono sine, expect ~0 LUFS): ${selfTest}`)

  let styles = await gg.evaluate(`
    const r = await fetch('http://127.0.0.1:8000/styles').then(r => r.json())
    return r.styles || r
  `)
  // GG_STYLES="a,b,c" — restrict to a subset (batching a long sweep into shorter runs).
  if (process.env.GG_STYLES) {
    const want = new Set(process.env.GG_STYLES.split(',').map(s => s.trim()).filter(Boolean))
    styles = styles.filter(s => want.has(s.id))
  }

  const results = []
  for (const s of styles) {
    const bpm = Math.round(((s.bpm_range?.[0] ?? 90) + (s.bpm_range?.[1] ?? 120)) / 2)
    const scale = s.default_scale || 'minor'
    const bars = 8
    try {
      const lufs = await withTimeout(gg.evaluate(`
        ${DSP}
        const gen = await fetch('http://127.0.0.1:8000/generate', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            style_id: ${JSON.stringify(s.id)}, key: 'C', scale: ${JSON.stringify(scale)}, bpm: ${bpm}, bars: ${bars},
            parts: ['chords', 'bass', 'melody', 'drums', 'pads'],
            mode: 'loop', seed: 42,
          }),
        }).then(r => r.json())
        const combined = (gen.files || []).find(f => f.part === 'combined')
        if (!combined) throw new Error('no combined file: ' + JSON.stringify(gen).slice(0, 200))
        const durationSeconds = ${bars} * 4 * 60 / ${bpm}
        const blob = await window.__gg.offlineRenderRaw(combined.url, ${JSON.stringify(s.id)}, durationSeconds, 'all', undefined, 'wav', null)
        const ab = await blob.arrayBuffer()
        const buf = await window.__gg.ctx().decodeAudioData(ab)
        const L = buf.getChannelData(0)
        const R = buf.numberOfChannels > 1 ? buf.getChannelData(1) : L
        return integratedLufs(L, R, buf.sampleRate)
      `), 40_000, s.id)
      results.push({ style: s.id, lufs: Math.round(lufs * 100) / 100 })
      console.log(`${s.id.padEnd(16)} ${lufs.toFixed(2)} LUFS`)
    } catch (e) {
      results.push({ style: s.id, error: String((e && e.message) || e) })
      console.log(`${s.id.padEnd(16)} ERROR: ${String((e && e.message) || e)}`)
    }
  }
  console.log(JSON.stringify({ selfTest, results }, null, 2))
}
