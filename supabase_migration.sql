-- Supabase Migration: poster/mapping tables
-- Run this in Supabase SQL Editor

-- 1. Mappings (hotspot → product linkage)
CREATE TABLE IF NOT EXISTS mappings (
    mapping_id   BIGSERIAL PRIMARY KEY,
    week_id      TEXT NOT NULL,
    flyer_filename TEXT NOT NULL,
    page_no      INTEGER NOT NULL,
    x0           DOUBLE PRECISION NOT NULL,
    y0           DOUBLE PRECISION NOT NULL,
    x1           DOUBLE PRECISION NOT NULL,
    y1           DOUBLE PRECISION NOT NULL,
    urun_kodu    TEXT,
    urun_aciklamasi TEXT,
    afis_fiyat   TEXT,
    ocr_text     TEXT,
    source       TEXT NOT NULL DEFAULT 'suggested',
    status       TEXT NOT NULL DEFAULT 'matched',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mappings_week ON mappings(week_id);
CREATE INDEX IF NOT EXISTS idx_mappings_page ON mappings(week_id, flyer_filename, page_no);

-- 2. Poster pages (metadata only — images go to Storage bucket)
CREATE TABLE IF NOT EXISTS poster_pages (
    id             BIGSERIAL PRIMARY KEY,
    week_id        TEXT NOT NULL,
    flyer_filename TEXT NOT NULL,
    page_no        INTEGER NOT NULL,
    image_path     TEXT NOT NULL DEFAULT '',
    title          TEXT DEFAULT '',
    sort_order     INTEGER DEFAULT 0,
    UNIQUE(week_id, flyer_filename, page_no)
);

CREATE INDEX IF NOT EXISTS idx_poster_pages_week ON poster_pages(week_id);

-- 3. Week products (Excel queue)
CREATE TABLE IF NOT EXISTS week_products (
    id              BIGSERIAL PRIMARY KEY,
    week_id         TEXT NOT NULL,
    urun_kodu       TEXT NOT NULL,
    urun_aciklamasi TEXT,
    afis_fiyat      TEXT,
    source_row      INTEGER DEFAULT 0,
    is_mapped       BOOLEAN DEFAULT FALSE,
    UNIQUE(week_id, urun_kodu)
);

CREATE INDEX IF NOT EXISTS idx_week_products_week ON week_products(week_id);

-- 4. Poster weeks (metadata)
CREATE TABLE IF NOT EXISTS poster_weeks (
    week_id     TEXT PRIMARY KEY,
    week_name   TEXT DEFAULT '',
    start_date  TEXT,
    end_date    TEXT,
    status      TEXT DEFAULT 'draft',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Storage bucket for poster images (run via Supabase dashboard or API)
-- INSERT INTO storage.buckets (id, name, public) VALUES ('poster-images', 'poster-images', true);
