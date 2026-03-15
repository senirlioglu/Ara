"""Mapping CRUD endpoints — fast upsert by bbox_hash."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text

from ..auth import verify_api_key
from ..db import get_db
from ..models import MappingCreate, MappingOut, BatchMappingRequest, Bbox

router = APIRouter()


@router.get("/{week_id}/pages/{flyer_id}/{page_no}/mappings", response_model=list[MappingOut])
async def get_mappings(week_id: str, flyer_id: str, page_no: int):
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT id, x0, y0, x1, y1, urun_kod, urun_ad, source, created_at
            FROM mappings
            WHERE week_id = :wid AND flyer_id = :fid AND page_no = :pno
            ORDER BY created_at
        """), {"wid": week_id, "fid": flyer_id, "pno": page_no})).mappings().all()

    return [
        MappingOut(
            id=str(r["id"]),
            bbox=Bbox(x0=r["x0"], y0=r["y0"], x1=r["x1"], y1=r["y1"]),
            urun_kod=r["urun_kod"],
            urun_ad=r["urun_ad"],
            source=r["source"],
            created_at=str(r["created_at"]),
        )
        for r in rows
    ]


@router.post(
    "/{week_id}/pages/{flyer_id}/{page_no}/mappings",
    dependencies=[Depends(verify_api_key)],
)
async def save_mapping(week_id: str, flyer_id: str, page_no: int, req: MappingCreate):
    bbox_hash = req.bbox.hash()

    async with get_db() as db:
        row = (await db.execute(text("""
            INSERT INTO mappings (week_id, flyer_id, page_no, x0, y0, x1, y1,
                                  bbox_hash, urun_kod, urun_ad, source)
            VALUES (:wid, :fid, :pno, :x0, :y0, :x1, :y1,
                    :bh, :kod, :ad, :src)
            ON CONFLICT (week_id, flyer_id, page_no, bbox_hash)
            DO UPDATE SET urun_kod = EXCLUDED.urun_kod,
                          urun_ad  = EXCLUDED.urun_ad,
                          source   = EXCLUDED.source,
                          updated_at = now()
            RETURNING id
        """), {
            "wid": week_id, "fid": flyer_id, "pno": page_no,
            "x0": req.bbox.x0, "y0": req.bbox.y0,
            "x1": req.bbox.x1, "y1": req.bbox.y1,
            "bh": bbox_hash,
            "kod": req.urun_kod, "ad": req.urun_ad, "src": req.source,
        })).mappings().first()

    return {"ok": True, "mapping_id": str(row["id"])}


@router.post("/{week_id}/mappings/batch", dependencies=[Depends(verify_api_key)])
async def save_mappings_batch(week_id: str, req: BatchMappingRequest):
    saved = 0
    async with get_db() as db:
        for item in req.items:
            bbox_hash = item.bbox.hash()
            await db.execute(text("""
                INSERT INTO mappings (week_id, flyer_id, page_no, x0, y0, x1, y1,
                                      bbox_hash, urun_kod, urun_ad, source)
                VALUES (:wid, :fid, :pno, :x0, :y0, :x1, :y1,
                        :bh, :kod, :ad, :src)
                ON CONFLICT (week_id, flyer_id, page_no, bbox_hash)
                DO UPDATE SET urun_kod = EXCLUDED.urun_kod,
                              urun_ad  = EXCLUDED.urun_ad,
                              source   = EXCLUDED.source,
                              updated_at = now()
            """), {
                "wid": week_id, "fid": item.flyer_id, "pno": item.page_no,
                "x0": item.bbox.x0, "y0": item.bbox.y0,
                "x1": item.bbox.x1, "y1": item.bbox.y1,
                "bh": bbox_hash,
                "kod": item.urun_kod, "ad": item.urun_ad, "src": item.source,
            })
            saved += 1

    return {"ok": True, "saved": saved}


@router.delete(
    "/{week_id}/mappings/{mapping_id}",
    dependencies=[Depends(verify_api_key)],
)
async def delete_mapping(week_id: str, mapping_id: str):
    async with get_db() as db:
        await db.execute(text(
            "DELETE FROM mappings WHERE id = :mid AND week_id = :wid"
        ), {"mid": mapping_id, "wid": week_id})
    return {"ok": True}
