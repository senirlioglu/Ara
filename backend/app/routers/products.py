"""Product search endpoint (server-side fallback)."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from ..db import get_db
from ..models import ProductOut

router = APIRouter()


@router.get("/{week_id}/products", response_model=list[ProductOut])
async def list_products(week_id: str):
    """Return all products for a week (UI caches this on first load)."""
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT urun_kod, urun_ad FROM products
            WHERE week_id = :wid ORDER BY urun_kod
        """), {"wid": week_id})).mappings().all()

    return [ProductOut(urun_kod=r["urun_kod"], urun_ad=r["urun_ad"]) for r in rows]


@router.get("/{week_id}/products/search", response_model=list[ProductOut])
async def search_products(week_id: str, q: str = ""):
    """Server-side search fallback — UI usually searches client-side."""
    if not q or len(q) < 2:
        return []

    norm_q = q.upper().replace("İ", "I").replace("Ş", "S").replace("Ğ", "G") \
               .replace("Ö", "O").replace("Ü", "U").replace("Ç", "C") \
               .replace("ı", "I").replace("ş", "S").replace("ğ", "G") \
               .replace("ö", "O").replace("ü", "U").replace("ç", "C").strip()

    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT urun_kod, urun_ad FROM products
            WHERE week_id = :wid
              AND (urun_kod ILIKE :q OR normalized ILIKE :nq)
            ORDER BY urun_kod
            LIMIT 50
        """), {"wid": week_id, "q": f"%{q}%", "nq": f"%{norm_q}%"})).mappings().all()

    return [ProductOut(urun_kod=r["urun_kod"], urun_ad=r["urun_ad"]) for r in rows]
