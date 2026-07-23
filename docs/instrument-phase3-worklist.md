# Instrument Identity — Phase 3 reconciliation decision sheet

**How to use:** audition each style in the app's Style Browser, then write the
instrument you want as the in-app preview in the **Pick** column (either name is
fine). Blank = not yet decided. When done, I rewire playback to the winners and
delete the frontend `STYLE_TO_INSTRUMENT` maps. Rows where both systems already
agree are omitted (no decision needed).

Legend: **In-app now** = what you hear today · **Registry** = what the
instrumentation block declares (drives the exported MIDI).

## Bass

| Style | In-app now | Registry | Pick |
|---|---|---|---|
| **ambient** | Fretless Bass | Synth Bass | Fretless Bass |
| **boom_bap** | Upright / Acoustic Bass | Electric Bass | Upright / Acoustic Bass |
| **cloud_rap** | Fretless Bass | 808 Sub | 808 Sub |
| **cumbia** | Upright / Acoustic Bass | Electric Bass | Upright / Acoustic Bass |
| **dancehall** | Electric Bass (finger) | Synth Bass | Synth Bass |
| **dark_ambient** | Fretless Bass | 808 Sub | 808 Sub |
| **dark_trap** | Electric Bass (pick) | 808 Sub | 808 Sub |
| **doom_metal** | Electric Bass (finger) *(default)* | Picked Bass | Electric Bass (finger) *(default)*|
| **drill** | Electric Bass (pick) | 808 Sub | 808 Sub |
| **funk** | Slap Bass | Electric Bass | Slap Bass |
| **hip_hop** | Electric Bass (finger) *(default)* | Synth Bass | Electric Bass (finger) |
| **lofi** | Fretless Bass | Electric Bass | Fretless Bass |
| **metal** | Electric Bass (finger) *(default)* | Picked Bass | Electric Bass (finger) *(default)* |
| **reggaeton** | Electric Bass (pick) | Synth Bass | Electric Bass (pick) |
| **rock** | Electric Bass (finger) *(default)* | Picked Bass | Electric Bass (finger) *(default)* |
| **trap_soul** | Electric Bass (finger) | 808 Sub | 808 Sub |

## Melodic (chords / lead bed)

> Note: the in-app melodic voice is one timbre for the whole melodic bed; the
> registry assigns a distinct instrument per part (chords vs melody). Shown: the
> registry's **chords** instrument (the harmonic bed you'd hear behind everything).

| Style | In-app now | Registry (chords) | Registry (melody) | Pick |
|---|---|---|---|---|
| **afrobeats** | Rhodes EP | Nylon Guitar | Marimba | Nylon Guitar |
| **afropop** | Drawbar Organ | Clean Electric Guitar | Marimba | Clean Electric Guitar |
| **ambient** | String Ensemble | Warm Pad | Flute | Flute |
| **dancehall** | Rhodes EP | Polysynth Pad | Vox Lead | Vox Lead |
| **dark_ambient** | String Ensemble | Bowed Pad | Oboe | Oboe |
| **funk** | Clavinet | Wurlitzer EP | Alto Sax | Alto Sax |
| **jazz** | Vibraphone | Rhodes EP | Alto Sax | Alto Sax |
| **latin_jazz** | Vibraphone | Jazz Guitar | Alto Sax | Jazz Guitar |
| **rnb** | Rhodes EP | Wurlitzer EP | Tenor Sax | Tenor Sax |
| **soul** | Rhodes EP | Wurlitzer EP | Tenor Sax | Tenor Sax |
| **trap_soul** | Rhodes EP | New Age Pad | Warm Pad | Warm Pad |

---

### Two structural gaps to decide once (apply across styles)

1. **Slap & fretless bass have no registry instrument.** Funk's `slap_bass_1`
   and lofi/cloud_rap/ambient/dark_ambient's `fretless_bass` can't be expressed
   by the registry today. Decide: add `slap_bass` + `fretless_bass` instruments
   to the registry (keeps those timbres), or let those styles fall back to the
   nearest existing bass (electric / 808). -> add `slap_bass` + `fretless_bass` instruments
   to the registry (keeps those timbres)
2. **17 styles have no in-app melodic entry** — they already fall through to
   generic synth families. Routing them through the registry would give each a
   curated per-part voice (pure gain, but new sound). Decide: opt them in now or
   leave as-is. -> opt in now
