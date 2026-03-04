"""Page listing endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from ..config import settings
from ..db import get_db
from ..models import PageOut

router = APIRouter()


@router.get("/{week_id}/pages", response_model=list[PageOut])
async def list_pages(week_id: str):
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT flyer_id, flyer_filename, page_no, image_path, status
            FROM pages
            WHERE week_id = :wid
            ORDER BY flyer_filename, page_no
        """), {"wid": week_id})).mappings().all()

    return [
        PageOut(
            flyer_id=r["flyer_id"],
            flyer_filename=r["flyer_filename"],
            page_no=r["page_no"],
            image_url=f"/static/weeks/{r['image_path']}" if r["image_path"] else None,
            status=r["status"],
        )
        for r in rows
    ]
