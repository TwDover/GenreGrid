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
    humanize: float = Field(default=0.5, ge=0.0, le=1.0)  # 0 = quantized, 1 = loose
    custom_progression: Optional[List[str]] = None  # e.g. ["i", "VI", "III", "VII"]
    blend_style_id: Optional[str] = None   # second style to blend with
    blend_amount: float = Field(default=0.5, ge=0.0, le=1.0)  # 0 = all primary, 1 = all blend


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


class StyleInfo(BaseModel):
    id: str
    name: str
    bpm_range: List[int] = [40, 240]
    default_scale: str = "minor"
    custom: bool = False


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
    register: float
    rhythm: float
    density: float
    mix: float
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
