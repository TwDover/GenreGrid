# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
from pydantic import BaseModel, Field
from typing import List, Optional


class GenerateRequest(BaseModel):
    style_id: str
    key: str = "C"
    scale: str = "minor"
    bpm: int = Field(default=140, ge=40, le=240)
    bars: int = Field(default=8, ge=1, le=128)
    complexity: float = Field(default=0.5, ge=0.0, le=1.0)
    variation: float = Field(default=0.4, ge=0.0, le=1.0)
    dynamics: float = Field(default=0.5, ge=0.0, le=1.0)  # arrangement drama: 0.5 = classic behavior, 0 = flat beat-tape, 1 = every drop/fill/lift pushed
    parts: List[str] = ["chords", "bass", "melody", "drums"]
    mode: str = "loop"   # "loop" | "arrangement"
    seed: Optional[int] = None
    section_type: Optional[str] = None  # intro | verse | pre_chorus | chorus | post_chorus | bridge | instrumental_solo | outro
    next_section_type: Optional[str] = None  # section that follows this one in a built song — sizes the drum fill/build at the boundary
    song_parts: Optional[List[str]] = None  # the FULL song's part list when this request is one section of a built song — register decisions (keeping chords below the melody) must stay consistent even in sections that drop the melody
    humanize: float = Field(default=0.5, ge=0.0, le=1.0)  # 0 = quantized, 1 = loose
    custom_progression: Optional[List[str]] = None  # e.g. ["i", "VI", "III", "VII"]
    blend_style_id: Optional[str] = None   # second style to blend with
    blend_amount: float = Field(default=0.5, ge=0.0, le=1.0)  # 0 = all primary, 1 = all blend
    use_priors: bool = True  # use a mined corpus prior (if one exists) for progression/melody; False forces templates


class RegeneratePartRequest(BaseModel):
    generation_id: str
    part: str
    style_id: str
    key: str = "C"
    scale: str = "minor"
    bpm: int = Field(default=140, ge=40, le=240)
    bars: int = Field(default=8, ge=1, le=128)
    complexity: float = Field(default=0.5, ge=0.0, le=1.0)
    variation: float = Field(default=0.4, ge=0.0, le=1.0)
    dynamics: float = Field(default=0.5, ge=0.0, le=1.0)  # must match the original generation for faithful drum replay
    mode: str = "arrangement"
    seed: int  # original seed — replayed to derive the same progression
    use_priors: bool = True


class StyleInfo(BaseModel):
    id: str
    name: str
    bpm_range: List[int] = [40, 240]
    default_scale: str = "minor"
    custom: bool = False
    has_prior: bool = False   # a mined corpus prior exists for this style
    instruments: dict[str, str] = {}   # part role → instrument display name ("melody": "Alto Sax")
    voices: dict[str, str] = {}        # part role → playback voice id ("melody": "melody_lead") — drives in-app audio


class FileInfo(BaseModel):
    part: str
    filename: str
    url: str


class GenerateSummary(BaseModel):
    key: str        # formatted label e.g. "C minor"
    key_root: str   # e.g. "C"
    scale: str      # e.g. "minor"
    bpm: int
    bars: int
    complexity: float
    variation: float
    mode: str
    section_type: Optional[str] = None


class QualityScore(BaseModel):
    total: float
    harmonic: float
    separation: float = 0.0   # register separation (renamed from 'register' — shadowed BaseModel.register)
    rhythm: float
    contour: float = 0.0
    density: float
    mix: float
    style_match: float = 0.0   # match to the genre's mined distribution (0 if no prior)
    hook: float = 0.0          # chorus memorability (0 if no chorus melody to judge)
    label: str
    flags: List[str]


class BatchGenerateRequest(BaseModel):
    base: "GenerateRequest"
    count: int = Field(default=4, ge=2, le=10)


class GenerateResponse(BaseModel):
    generation_id: str
    style: str
    files: List[FileInfo]
    summary: GenerateSummary
    seed: int
    quality: Optional[QualityScore] = None
    auto_saved: bool = False
    progression: list[str] = []


class SongSectionDef(BaseModel):
    """One section of a custom song template."""
    section_type: str  # intro | verse | pre_chorus | chorus | post_chorus | bridge | instrumental_solo | outro
    bars: int = Field(default=8, ge=1, le=32)
    name: Optional[str] = None
    parts_mode: str = "full"  # full | no_arp | sparse | foundation | melodic | no_drums | chords_only
    chorus_key: bool = False
    bridge_key: bool = False
    style_id: Optional[str] = None  # per-section style override (e.g. a lofi verse into a house chorus)


class BuildSongRequest(BaseModel):
    style_id: str
    key: str = "C"
    scale: str = "minor"
    bpm: int = Field(default=120, ge=40, le=240)
    complexity: float = Field(default=0.6, ge=0.0, le=1.0)
    variation: float = Field(default=0.4, ge=0.0, le=1.0)
    dynamics: float = Field(default=0.5, ge=0.0, le=1.0)  # arrangement drama: scales drops/fills/breakdowns/section contrast; 0.5 = classic
    humanize: float = Field(default=0.5, ge=0.0, le=1.0)
    parts: List[str] = ["chords", "bass", "melody", "drums"]
    template: str = "verse_chorus"
    seed: Optional[int] = None
    use_priors: bool = True
    chorus_key_shift: Optional[int] = Field(default=None, ge=-12, le=12)  # semitone lift on chorus sections; None = use the style's default
    bridge_key_shift: Optional[int] = Field(default=None, ge=-12, le=12)  # semitone shift on bridge sections; None = use the style's default (5 = subdominant lift)
    final_chorus_lift: Optional[int] = Field(default=None, ge=-12, le=12)  # extra semitone lift on the LAST chorus only (gear change); None = style default (+1)
    custom_template: Optional[List[SongSectionDef]] = Field(default=None, max_length=20)  # overrides `template` when provided
    blend_style_id: Optional[str] = None   # second style blended into the whole song
    blend_amount: float = Field(default=0.5, ge=0.0, le=1.0)
    dj_edit: bool = False   # prepend/append an 8-bar beat-only (drums+bass) DJ intro/outro for mixing
    progression_override: Optional[List[str]] = Field(default=None, max_length=32)  # pin an explicit roman-numeral progression, bypassing the style pool


class RegenerateSongPartRequest(BaseModel):
    generation_id: str
    part: str


class RegenerateSongSectionRequest(BaseModel):
    generation_id: str
    section_index: int  # index into the song's template sections (the ending bar is not re-rollable)
    locked_parts: List[str] = []  # parts to leave byte-identical — the section re-roll regenerates only the rest


class RollSongPartRequest(BaseModel):
    generation_id: str
    part: str
    count: int = Field(default=3, ge=2, le=4)  # how many candidate variations to roll


class SongPartCandidate(BaseModel):
    index: int
    filename: str
    url: str


class KeepSongPartCandidateRequest(BaseModel):
    generation_id: str
    part: str
    index: int  # which rolled candidate to promote to the live stem


class RebuildSongProgressionRequest(BaseModel):
    generation_id: str
    progression: List[str] = Field(..., min_length=2, max_length=32)  # the user-edited roman-numeral progression


class RestoreSongVersionRequest(BaseModel):
    generation_id: str
    version_id: str  # millisecond-timestamp folder name from /song-versions


class SetPartGainRequest(BaseModel):
    generation_id: str
    part: str
    gain: float = Field(default=1.0, ge=0.1, le=2.0)  # 1.0 = as generated


class EditedNote(BaseModel):
    """One note of a hand-edited stem (times in beats, like NoteEvent)."""
    pitch: int = Field(ge=0, le=127)
    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    velocity: int = Field(ge=1, le=127)


class EditPartRequest(BaseModel):
    """Replace a song stem's notes with a hand-edited list (piano-roll editing)."""
    generation_id: str
    part: str
    notes: list[EditedNote] = Field(max_length=5000)


class SongSectionResult(BaseModel):
    name: str
    section_type: str
    bars: int
    start_bar: int
    key: str
    quality: Optional[float] = None  # composite quality score (0-1) of the section's winning attempt


class BuildSongResponse(BaseModel):
    generation_id: str
    style: str
    files: List[FileInfo]
    seed: int
    template: str
    total_bars: int
    sections: List[SongSectionResult]
    bpm: int
    key: str
    progression: Optional[List[str]] = None  # resolved roman-numeral progression (shown + lockable in the UI)
    mixer: Optional[dict] = None  # per-part gain (1.0 = as generated), persisted in song_meta
