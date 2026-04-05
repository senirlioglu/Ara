"""Week-level endpoints: ingest, status."""

from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy import text

from ..auth import verify_api_key
from ..db import get_db
from ..models import IngestRequest, WeekStatus

router = APIRouter()


@router.post("/{week_id}/ingest", dependencies=[Depends(verify_api_key)])
async def ingest_week(week_id: str, req: IngestRequest):
    """Queue PDF rendering + product import for a week."""
    async with get_db() as db:
        # Upsert week row
        await db.execute(text("""
            INSERT INTO weeks (week_id, status)
            VALUES (:wid, 'INGESTING')
            ON CONFLICT (week_id) DO UPDATE SET status='INGESTING', updated_at=now()
        """), {"wid": week_id})

        # Insert page stubs for each PDF page (actual render happens in worker)
        for pdf in req.pdfs:
            await db.execute(text("""
                INSERT INTO pages (week_id, flyer_id, flyer_filename, page_no, status)
                VALUES (:wid, :fid, :fname, 1, 'NEW')
                ON CONFLICT (week_id, flyer_id, page_no) DO NOTHING
            """), {"wid": week_id, "fid": pdf.flyer_id, "fname": pdf.filename})

    # TODO: queue render_week_job(week_id) via Redis/RQ/Celery
    #   from ..services.render import render_week_job
    #   render_week_job.delay(week_id)

    return {"status": "queued", "week_id": week_id}


@router.post("/{week_id}/upload-pdf", dependencies=[Depends(verify_api_key)])
async def upload_pdf(
    week_id: str,
    flyer_id: str = Form(...),
    file: UploadFile = File(...),
):
    """Upload a single PDF file for rendering."""
    from ..services.render import save_pdf_and_render

    pdf_bytes = await file.read()
    result = await save_pdf_and_render(week_id, flyer_id, file.filename, pdf_bytes)
    return result


@router.post("/{week_id}/upload-excel", dependencies=[Depends(verify_api_key)])
async def upload_excel(
    week_id: str,
    file: UploadFile = File(...),
):
    """Upload Excel product list for a week."""
    from ..services.products import import_excel_bytes

    excel_bytes = await file.read()
    count = await import_excel_bytes(week_id, excel_bytes)
    return {"week_id": week_id, "imported": count}


@router.get("/{week_id}/status")
async def week_status(week_id: str) -> WeekStatus:
    async with get_db() as db:
        # Page counts
        row = (await db.execute(text("""
            SELECT
                count(*) AS total,
                count(*) FILTER (WHERE status='READY') AS ready,
                count(*) FILTER (WHERE status='FAILED') AS failed
            FROM pages WHERE week_id = :wid
        """), {"wid": week_id})).mappings().first()

        # Product count
        prow = (await db.execute(text(
            "SELECT count(*) AS cnt FROM products WHERE week_id = :wid"
        ), {"wid": week_id})).mappings().first()

        # Week row
        wrow = (await db.execute(text(
            "SELECT status FROM weeks WHERE week_id = :wid"
        ), {"wid": week_id})).mappings().first()

    return WeekStatus(
        week_id=week_id,
        status=wrow["status"] if wrow else "NOT_FOUND",
        render_status={
            "total_pages": row["total"] if row else 0,
            "ready_pages": row["ready"] if row else 0,
            "failed_pages": row["failed"] if row else 0,
        },
        product_status={
            "loaded": (prow["cnt"] if prow else 0) > 0,
            "count": prow["cnt"] if prow else 0,
        },
    )
