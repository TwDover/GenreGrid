from pydantic import BaseModel, Field
from typing import List, Optional


class GenerateRequest(BaseModel):
    style_id: str
    key: str = "C"
    scale: str = "minor"
    bpm: int = Field(default=140, ge=40, le=240)
    bars: int = Field(default=8, ge=1, le=32)
    complexity: float = Field(default=0.5, ge=0.0, le=1.0)
    variation: float = Field(default=0.4, ge=0.0, le=1.0)
    parts: List[str] = ["chords", "bass", "melody", "drums"]


class StyleInfo(BaseModel):
    id: str
    name: str


class FileInfo(BaseModel):
    part: str
    filename: str
    url: str


class GenerateSummary(BaseModel):
    key: str
    bpm: int
    bars: int


class GenerateResponse(BaseModel):
    generation_id: str
    style: str
    files: List[FileInfo]
    summary: GenerateSummary
