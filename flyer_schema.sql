-- ============================================================================
-- FLYER PIPELINE v3 — Price-Anchored Product Regions (Lens-like)
-- PDF → OCR → Price Detection → Region Building → Excel Matching
-- ============================================================================

-- 1. WEEKS (unchanged)
CREATE TABLE IF NOT EXISTS weeks (
    week_id     SERIAL PRIMARY KEY,
    week_date   DATE NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_weeks_date ON weeks (week_date DESC);

-- 2. WEEKLY_PRODUCTS: Excel ürün listesi (hafta başına 1 kez import)
CREATE TABLE IF NOT EXISTS weekly_products (
    id              SERIAL PRIMARY KEY,
    week_id         INTEGER NOT NULL REFERENCES weeks(week_id) ON DELETE CASCADE,
    urun_kodu       TEXT,
    urun_aciklamasi TEXT,
    afis_fiyat      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_weekly_products_week ON weekly_products (week_id);
CREATE INDEX IF NOT EXISTS idx_weekly_products_kod  ON weekly_products (urun_kodu);

-- 3. FLYERS: Her PDF sayfası bir flyer kaydı
CREATE TABLE IF NOT EXISTS flyers (
    flyer_id     SERIAL PRIMARY KEY,
    week_id      INTEGER NOT NULL REFERENCES weeks(week_id) ON DELETE CASCADE,
    pdf_filename TEXT NOT NULL,
    page_no      INTEGER NOT NULL DEFAULT 1,
    image_url    TEXT,                          -- Supabase Storage URL (rendered PNG)
    img_w        INTEGER,                       -- Render genişliği (px)
    img_h        INTEGER,                       -- Render yüksekliği (px)
    zoom         REAL DEFAULT 3.5,              -- PyMuPDF render zoom
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_flyers_week ON flyers (week_id);

-- 4. FLYER_OCR: Vision OCR kelime cache (flyer/sayfa başına 1 kayıt)
--    ocr_words: [{text, x0, y0, x1, y1}, ...] piksel koordinat
CREATE TABLE IF NOT EXISTS flyer_ocr (
    flyer_id    INTEGER PRIMARY KEY REFERENCES flyers(flyer_id) ON DELETE CASCADE,
    ocr_words   JSONB NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 5. FLYER_REGIONS: Fiyat-ankorlu ürün bölgeleri
CREATE TABLE IF NOT EXISTS flyer_regions (
    region_id    SERIAL PRIMARY KEY,
    flyer_id     INTEGER NOT NULL REFERENCES flyers(flyer_id) ON DELETE CASCADE,
    price_value  TEXT,                          -- Algılanan fiyat (ör. "42.999")
    price_bbox   JSONB,                        -- Fiyat kelimesinin bbox {x0,y0,x1,y1} px
    x0           REAL NOT NULL,                -- Normalize bölge bbox (0..1)
    y0           REAL NOT NULL,
    x1           REAL NOT NULL,
    y1           REAL NOT NULL,
    region_text  TEXT,                          -- Bölgedeki tüm OCR text
    keys_json    JSONB DEFAULT '{}',           -- {model_codes, code4, brands, sizes, prices}
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_flyer_regions_flyer ON flyer_regions (flyer_id);

-- 6. FLYER_MATCHES: Bölge ↔ Excel eşleşmeleri
CREATE TABLE IF NOT EXISTS flyer_matches (
    match_id         SERIAL PRIMARY KEY,
    region_id        INTEGER NOT NULL REFERENCES flyer_regions(region_id) ON DELETE CASCADE,
    urun_kodu        TEXT,
    urun_aciklamasi  TEXT,
    afis_fiyat       TEXT,
    confidence       REAL DEFAULT 0,
    status           TEXT DEFAULT 'pending'
                     CHECK (status IN ('pending','matched','review','unmatched')),
    candidates_json  JSONB DEFAULT '[]',       -- Top 5 aday [{urun_kodu, score, ...}]
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_flyer_matches_region ON flyer_matches (region_id);
CREATE INDEX IF NOT EXISTS idx_flyer_matches_status ON flyer_matches (status);

-- Auto-update trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_flyer_matches_updated ON flyer_matches;
CREATE TRIGGER trg_flyer_matches_updated
    BEFORE UPDATE ON flyer_matches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
