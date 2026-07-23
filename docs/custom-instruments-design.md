# Design: User-uploaded custom instruments

**Status (2026-07-23): MVP IMPLEMENTED (needs desktop runtime testing).** Design for
letting users add their own samples, map them to notes/velocities, and pick which
instrument plays each part. Fleshes out the Phase 2 roadmap item "Custom soundfont /
SF2 upload + per-part instrument picker."

**Shipped (T1 + T2 tier):** pure mapping core (`customInstruments.ts`, unit-tested),
library store (`useCustomInstruments.ts`), Electron storage IPC + preload (list/save/
remove/read under `userData/instruments/`, played back as blob: URLs — no custom
scheme, per the Linux Web-Audio note below), engine integration (every part resolves a
custom instrument first in `useMidiPlayer.ts`), and the Instruments panel UI + a 🎹
transport-bar button. **Not yet done:** velocity-layer preview, SF2/SFZ import (T4),
auto pitch-detection, per-style-override UI, web/OPFS storage. **Untested at runtime**
(automation can't launch Electron / play audio) — needs a desktop pass: import a file,
assign it to a part, play, and delete.

## Why now

The July 2026 license pass removed the MusyngKite bass/melodic samples, so 13 voices
now synthesize (see [`LICENSE_AUDIT.md`](LICENSE_AUDIT.md)). Letting users bring their
own samples both restores instrument realism **and sidesteps the licensing problem** —
user-supplied audio is the user's to use, nothing we ship. It also builds directly on
the two seams already in place: the `LayeredSampler` **manifest format** and the
**registry** (`voiceFor(styleId, part)`) that resolves each part to a voice id.

## Core concept

> A **Custom Instrument** is just a `LayeredSampler` manifest + its audio files, given a
> voice id, that the user can select for any part.

**Every part/voice is user-samplable — no exceptions.** Chords, melody, arpeggio, bass,
pads, and counter-melody can each be driven by a user instrument, including the voices
that currently synthesize. There is no "these are sampled, those are synth-only" split at
the user level: the per-part picker offers a user instrument for *any* part, and a user
instrument can replace a built-in voice entirely. (Custom drum *kits* use a pitch→one-shot
mapping rather than a chromatic range, so they get a dedicated editor in a later phase, but
they are still in scope as user-uploadable.)

Nothing new in the audio engine — `LayeredSampler` already plays a `velocity.json`
manifest (note → file(s), velocity layers, round-robins). A custom instrument is that
same structure, sourced from user files instead of `/samples/`. The registry's job
("what voice does this part use?") gains a third answer: built-in sample set, synth
family, **or a user instrument**.

---

## Key decisions (with options + recommendation)

### 1. Upload format & note mapping — *how do files become a playable instrument?*

The hard part of "easy and manageable" is note/velocity mapping. Recommend a **tiered**
approach so the easy case is trivial and quality scales up, all producing one manifest:

| Tier | User does | We do | For |
|---|---|---|---|
| **T1 — one shot** | Drop **one** audio file | Map it across the keyboard, pitch-shifted (single-zone `Tone.Sampler`) | Casual: "make an instrument from this sound" |
| **T2 — named files** | Drop files named by note (`C4.wav`, `A#3.wav`, `Fs3…`) | Parse note from filename → multi-zone manifest | Better realism, minimal effort |
| **T3 — velocity/RR** | Files with velocity/RR suffix or in `soft/`,`hard/` subfolders (our pipeline's convention) | Build layered manifest | Full dynamics — matches `build_velocity_samples.py` output |
| **T4 — soundfont** | Upload `.sf2` / `.sfz` | Parse zones/velocity splits → manifest (+ decode samples) | Import existing libraries |

- **Recommendation:** ship **T1 + T2** as the MVP (covers "easy and manageable" and
  reuses the manifest 1:1), then **T3** (already produced by our own pipeline), then
  **T4** last (SF2/SFZ parsing is the heaviest — needs a parser + sample decode; SFZ is
  text-simple, SF2 is binary and benefits from a lib like `soundfont2`).
- A drag-drop **zip or folder** import wraps T2/T3 (one gesture, many files).
- **Optional polish:** auto pitch-detection (detect fundamental) to relax the filename
  requirement in T1/T2 — nice, not required for MVP.

### 2. Assignment model — *which instrument belongs to which part?*

- **Option A — Instrument-first (recommended):** the user creates a named, reusable
  instrument ("My Rhodes") in a library, then assigns it to parts via a **per-part
  instrument picker**. One instrument, usable across styles/parts.
- **Option B — Part-first:** the user opens a part ("Bass") and uploads for it directly.
  Simpler mental model but not reusable; leads to re-uploading the same sound per style.
- **Recommendation: A.** It matches the registry (voices are reusable identities) and
  makes the per-part picker a pure selection surface. The picker for each part
  (chords / melody / arpeggio / bass / pads / counter-melody) offers: **Synth · Built-in
  sample · [user instruments…]**, extending today's `sampleMode` toggle from a global
  2-way switch into a per-part source choice.

### 3. Storage & serving — *where do the files live and how does Tone load them?*

Uploaded audio is **user data**, never bundled. `Tone.Sampler` needs a fetchable URL.

- **Electron (primary):** store under `app.getPath('userData')/instruments/<id>/` with a
  `manifest.json` per instrument + a top-level `index.json`. Serve to the renderer via a
  **custom protocol** (`protocol.handle('gginstr', …)`) → stable, cacheable URLs
  (`gginstr://<id>/<file>`) that `LayeredSampler` fetches like `/samples/…`. Cleaner than
  IPC-read → object URLs, and respects `contextIsolation` + CSP (add the scheme to CSP).
- **Web build (fallback):** **OPFS** (Origin Private File System) for the bytes + object
  URLs, or IndexedDB blobs. Same manifest shape.
- **Recommendation:** custom protocol in Electron; OPFS in the browser. Both hand
  `LayeredSampler` a URL, so the engine is storage-agnostic.

### 4. Persistence of assignments

A small user settings object (persisted like `sampleMode`): a default per-part
instrument map, with optional per-style overrides. Resolution order at play time:
**per-style user override → global user default → registry `voiceFor` → synth fallback.**

---

## Data model

```ts
interface CustomInstrument {
  id: string            // uuid; also the voice id and storage folder
  name: string          // "My Rhodes"
  kind: 'melodic' | 'bass' | 'drums'
  manifest: LayeredSamplerManifest   // note → file(s), velocity layers, RR
  createdAt: number
}
// index.json: CustomInstrument[] (without the audio bytes)

interface InstrumentAssignments {
  defaults: Partial<Record<PlayerPart, string>>              // part → instrument id
  perStyle?: Record<string /*styleId*/, Partial<Record<PlayerPart, string>>>
}
```

## Integration points (all already exist)

- **Engine:** `LayeredSampler` (`layeredSampler.ts`) — unchanged; loads a user manifest
  by base URL. `loadLayeredSampler` already fetches `velocity.json`; a user instrument
  supplies the same shape.
- **Resolution:** extend the `voiceFor(...)` consumers in `useMidiPlayer.ts` to first
  consult `InstrumentAssignments`, then fall through to the registry, then synth.
- **Mode:** generalize `sampleMode` (`useMidiPlayer.ts`) — 'synth' | 'samples' stays as
  the global default; the per-part picker overrides it per part.
- **UI:** a new **Instruments** drawer/panel (library CRUD + upload + mapping preview)
  and a compact per-part picker on `PartCard.vue` / the transport.
- **Electron:** custom protocol registration + an IPC surface for import/list/delete
  (reuse the `save-temp-file` basename-hardening pattern for uploaded filenames).

## Phased delivery

1. **MVP** — Instruments library (list/add/delete) + T1 (one-shot) & T2 (note-named)
   import + Electron protocol storage + per-part picker wired into playback. Piano/
   vibraphone remain the built-in sampled voices; users fill the rest.
2. **Velocity layers (T3)** + a light mapping preview (mini keyboard, hear each zone).
3. **SF2/SFZ import (T4)** — start with SFZ (text), then SF2 via a parser.
4. **Polish** — auto pitch-detection, per-style overrides UI, export/share an instrument
   as a zip (round-trips with `build_velocity_samples.py` output).

## Open questions / risks

- **Formats to accept:** wav/mp3/ogg/flac? (Web Audio decodes all; storage size varies —
  maybe transcode-to-ogg on import to bound footprint.)
- **CSP:** the custom scheme must be allowed for media without weakening the existing
  localhost-only policy.
- **Large libraries:** memory/CPU if a user loads many big multisamples — lazy-load per
  style, cap total decoded buffers.
- **Drums:** custom drum *kits* map pitch→one-shot, not a chromatic range — likely a
  separate, later editor from the melodic flow.
