"""Pydantic models — API request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Bbox ──
class Bbox(BaseModel):
    x0: float = Field(..., ge=0, le=1)
    y0: float = Field(..., ge=0, le=1)
    x1: float = Field(..., ge=0, le=1)
    y1: float = Field(..., ge=0, le=1)

    def hash(self) -> str:
        return f"{self.x0:.4f},{self.y0:.4f},{self.x1:.4f},{self.y1:.4f}"


# ── Pages ──
class PageOut(BaseModel):
    flyer_id: str
    flyer_filename: str
    page_no: int
    image_url: str | None
    status: str


# ── Products ──
class ProductOut(BaseModel):
    urun_kod: str
    urun_ad: str | None
    score: float | None = None


# ── Mappings ──
class MappingCreate(BaseModel):
    bbox: Bbox
    urun_kod: str
    urun_ad: str | None = None
    source: str = "excel"   # "excel" | "manual"


class MappingOut(BaseModel):
    id: str
    bbox: Bbox
    urun_kod: str | None
    urun_ad: str | None
    source: str
    created_at: str


class BatchMappingItem(BaseModel):
    flyer_id: str
    page_no: int
    bbox: Bbox
    urun_kod: str
    urun_ad: str | None = None
    source: str = "excel"


class BatchMappingRequest(BaseModel):
    items: list[BatchMappingItem]


# ── Ingest ──
class PdfIngest(BaseModel):
    flyer_id: str
    filename: str
    pdf_url: str | None = None
    # Alternative: pdf will be uploaded as file


class IngestRequest(BaseModel):
    pdfs: list[PdfIngest] = []
    excel_url: str | None = None


# ── Week Status ──
class WeekStatus(BaseModel):
    week_id: str
    status: str
    render_status: dict
    product_status: dict
