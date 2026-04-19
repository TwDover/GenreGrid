/**
 * Encode a Web Audio AudioBuffer to a 16-bit PCM WAV Blob.
 * WAV header is 44 bytes; audio data follows as interleaved little-endian int16.
 */
export function encodeWav(audioBuffer: AudioBuffer): Blob {
  const ch = audioBuffer.numberOfChannels
  const sr = audioBuffer.sampleRate
  const dataLen = audioBuffer.length * ch * 2  // 2 bytes per sample (int16)
  const ab = new ArrayBuffer(44 + dataLen)
  const v = new DataView(ab)

  function str(off: number, s: string) {
    for (let i = 0; i < s.length; i++) v.setUint8(off + i, s.charCodeAt(i))
  }

  str(0, 'RIFF');  v.setUint32(4,  36 + dataLen, true)
  str(8, 'WAVE'); str(12, 'fmt ')
  v.setUint32(16, 16, true)          // fmt chunk size
  v.setUint16(20,  1, true)          // PCM
  v.setUint16(22, ch, true)
  v.setUint32(24, sr, true)
  v.setUint32(28, sr * ch * 2, true) // byte rate
  v.setUint16(32, ch * 2, true)      // block align
  v.setUint16(34, 16, true)          // bits per sample
  str(36, 'data'); v.setUint32(40, dataLen, true)

  let off = 44
  for (let i = 0; i < audioBuffer.length; i++) {
    for (let c = 0; c < ch; c++) {
      const s = Math.max(-1, Math.min(1, audioBuffer.getChannelData(c)[i]))
      v.setInt16(off, s < 0 ? s * 32768 : s * 32767, true)
      off += 2
    }
  }

  return new Blob([ab], { type: 'audio/wav' })
}
