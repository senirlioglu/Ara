-- ============================================================================
-- Mapping Engine — Database Schema (PostgreSQL / Supabase)
-- ============================================================================
-- Run once against your Postgres instance.
-- Compatible with Supabase (just paste into SQL Editor).
-- ============================================================================

-- 1. PAGES — rendered PDF page images
CREATE TABLE IF NOT EXISTS pages (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    week_id       TEXT        NOT NULL,
    flyer_id      TEXT        NOT NULL,
    flyer_filename TEXT       NOT NULL,
    page_no       INTEGER     NOT NULL,
    image_path    TEXT,                          -- relative: weeks/{week_id}/{flyer_id}/page_001.jpg
    width_px      INTEGER,
    height_px     INTEGER,
    status        TEXT        NOT NULL DEFAULT 'NEW',   -- NEW | RENDERING | READY | FAILED
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (week_id, flyer_id, page_no)
);

CREATE INDEX idx_pages_week     ON pages (week_id);
CREATE INDEX idx_pages_status   ON pages (week_id, status);

-- 2. PRODUCTS — Excel ürün listesi (haftalık)
CREATE TABLE IF NOT EXISTS products (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    week_id       TEXT    NOT NULL,
    urun_kod      TEXT    NOT NULL,
    urun_ad       TEXT,
    normalized    TEXT,                          -- arama için: lower + tr-normalize + strip
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (week_id, urun_kod)
);

CREATE INDEX idx_products_week  ON products (week_id);
CREATE INDEX idx_products_norm  ON products (week_id, normalized);

-- 3. MAPPINGS — bbox ↔ ürün eşleştirmeleri
CREATE TABLE IF NOT EXISTS mappings (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    week_id       TEXT    NOT NULL,
    flyer_id      TEXT    NOT NULL,
    page_no       INTEGER NOT NULL,
    x0            REAL    NOT NULL,
    y0            REAL    NOT NULL,
    x1            REAL    NOT NULL,
    y1            REAL    NOT NULL,
    bbox_hash     TEXT    NOT NULL,              -- deterministic: f"{x0:.4f},{y0:.4f},{x1:.4f},{y1:.4f}"
    urun_kod      TEXT,
    urun_ad       TEXT,
    source        TEXT    NOT NULL DEFAULT 'excel',  -- excel | manual
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (week_id, flyer_id, page_no, bbox_hash)
);

CREATE INDEX idx_mappings_page  ON mappings (week_id, flyer_id, page_no);

-- 4. WEEKS — hafta metadata + durum takibi
CREATE TABLE IF NOT EXISTS weeks (
    week_id       TEXT PRIMARY KEY,
    status        TEXT    NOT NULL DEFAULT 'CREATED',  -- CREATED | INGESTING | READY | FAILED
    total_pages   INTEGER DEFAULT 0,
    ready_pages   INTEGER DEFAULT 0,
    product_count INTEGER DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
