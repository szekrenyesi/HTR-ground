"""
A belső, normalizált HTR oldal-reprezentáció.

Pontosan ezt a struktúrát várja a frontend (editor.html).
A különböző bemeneti formátumok (ALTO XML, PAGE XML, natív JSON)
mind ide konvertálódnak.

A koordináták a forrás kép natív pixelterében értelmezettek.
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


Point = List[float]  # [x, y]
Rect = List[float]   # [x, y, w, h]


class Line(BaseModel):
    coords: List[Point]                # poligon
    rect: Rect                          # bounding box [x, y, w, h]
    baseline: Optional[List[Point]] = None  # opcionális, [[x1,y1], [x2,y2], ...]
    text: str = ""


class Region(BaseModel):
    coords: List[Point]
    rect: Rect
    lines: List[Line] = Field(default_factory=list)


class Page(BaseModel):
    regions: List[Region] = Field(default_factory=list)
    # Opcionális metaadatok — a frontend egyelőre nem használja, de visszafejtéshez hasznos
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    source_format: Optional[str] = None  # "alto-xml" | "page-xml" | "json"
