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
    parts: List[str] = ["chords", "bass", "melody", "drums"]
    mode: str = "loop"   # "loop" | "arrangement"
    seed: Optional[int] = None
    section_type: Optional[str] = None  # intro | verse | pre_chorus | chorus | post_chorus | bridge | instrumental_solo | outro
    next_section_type: Optional[str] = None  # section that follows this one in a built song — sizes the drum fill/build at the boundary
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


class BuildSongRequest(BaseModel):
    style_id: str
    key: str = "C"
    scale: str = "minor"
    bpm: int = Field(default=120, ge=40, le=240)
    complexity: float = Field(default=0.6, ge=0.0, le=1.0)
    variation: float = Field(default=0.4, ge=0.0, le=1.0)
    humanize: float = Field(default=0.5, ge=0.0, le=1.0)
    parts: List[str] = ["chords", "bass", "melody", "drums"]
    template: str = "verse_chorus"
    seed: Optional[int] = None
    use_priors: bool = True
    chorus_key_shift: Optional[int] = Field(default=None, ge=-12, le=12)  # semitone lift on chorus sections; None = use the style's default
    bridge_key_shift: Optional[int] = Field(default=None, ge=-12, le=12)  # semitone shift on bridge sections; None = use the style's default (5 = subdominant lift)


class RegenerateSongPartRequest(BaseModel):
    generation_id: str
    part: str


class SongSectionResult(BaseModel):
    name: str
    section_type: str
    bars: int
    start_bar: int
    key: str


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
