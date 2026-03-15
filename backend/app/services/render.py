"""PDF rendering service — converts PDF pages to JPG on disk."""

from __future__ import annotations

import logging
from pathlib import Path

import fitz  # PyMuPDF

from ..config import settings

log = logging.getLogger(__name__)


def render_pdf_to_disk(
    week_id: str,
    flyer_id: str,
    pdf_bytes: bytes,
    zoom: float | None = None,
    quality: int | None = None,
) -> list[dict]:
    """Render all pages of a PDF to JPG files on disk.

    Returns list of {page_no, image_path, width, height}.
    image_path is relative to DATA_DIR (e.g. "weeks/2024-03-01/abc/page_001.jpg").
    """
    zoom = zoom or settings.RENDER_ZOOM
    quality = quality or settings.JPEG_QUALITY

    out_dir = settings.weeks_dir / week_id / flyer_id
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    mat = fitz.Matrix(zoom, zoom)
    pages = []

    for i in range(len(doc)):
        pix = doc[i].get_pixmap(matrix=mat, alpha=False)
        fname = f"page_{i + 1:03d}.jpg"
        fpath = out_dir / fname
        pix.save(str(fpath), output="jpeg", jpg_quality=quality)

        rel_path = f"{week_id}/{flyer_id}/{fname}"
        pages.append({
            "page_no": i + 1,
            "image_path": rel_path,
            "width": pix.width,
            "height": pix.height,
        })
        log.info("Rendered %s page %d → %s (%dx%d)", flyer_id, i + 1, fpath, pix.width, pix.height)

    doc.close()
    return pages


async def save_pdf_and_render(
    week_id: str,
    flyer_id: str,
    filename: str,
    pdf_bytes: bytes,
) -> dict:
    """Save PDF, render pages, insert into DB.  Runs synchronously for now.

    For production, move rendering to a Celery/RQ/Arq worker.
    """
    import asyncio
    from sqlalchemy import text
    from ..db import get_db

    # Render (CPU-bound — run in thread pool)
    rendered = await asyncio.to_thread(
        render_pdf_to_disk, week_id, flyer_id, pdf_bytes,
    )

    # Insert into DB
    async with get_db() as db:
        # Upsert week
        await db.execute(text("""
            INSERT INTO weeks (week_id, status)
            VALUES (:wid, 'READY')
            ON CONFLICT (week_id) DO UPDATE SET updated_at = now()
        """), {"wid": week_id})

        for p in rendered:
            await db.execute(text("""
                INSERT INTO pages (week_id, flyer_id, flyer_filename, page_no,
                                   image_path, width_px, height_px, status)
                VALUES (:wid, :fid, :fname, :pno, :ipath, :w, :h, 'READY')
                ON CONFLICT (week_id, flyer_id, page_no)
                DO UPDATE SET image_path = EXCLUDED.image_path,
                              width_px   = EXCLUDED.width_px,
                              height_px  = EXCLUDED.height_px,
                              status     = 'READY',
                              updated_at = now()
            """), {
                "wid": week_id, "fid": flyer_id, "fname": filename,
                "pno": p["page_no"], "ipath": p["image_path"],
                "w": p["width"], "h": p["height"],
            })

        # Update week page counts
        await db.execute(text("""
            UPDATE weeks SET
                total_pages = (SELECT count(*) FROM pages WHERE week_id = :wid),
                ready_pages = (SELECT count(*) FROM pages WHERE week_id = :wid AND status = 'READY'),
                updated_at = now()
            WHERE week_id = :wid
        """), {"wid": week_id})

    return {
        "ok": True,
        "week_id": week_id,
        "flyer_id": flyer_id,
        "pages_rendered": len(rendered),
    }
