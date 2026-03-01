-- ============================================================================
-- FLYER PIPELINE v2 — Vision OCR + DBSCAN Clustering + Matching
-- Haftalık afiş görselleri üzerinden otomatik ürün bölgesi tespiti
-- ============================================================================

-- 1. WEEKS: Hafta kayıtları
CREATE TABLE IF NOT EXISTS weeks (
    week_id     SERIAL PRIMARY KEY,
    week_date   DATE NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_weeks_date ON weeks (week_date DESC);

-- 2. FLYERS: Her hafta yüklenen afiş görselleri
CREATE TABLE IF NOT EXISTS flyers (
    flyer_id    SERIAL PRIMARY KEY,
    week_id     INTEGER NOT NULL REFERENCES weeks(week_id) ON DELETE CASCADE,
    filename    TEXT NOT NULL,
    image_url   TEXT,                          -- Supabase Storage public URL
    img_w       INTEGER,                       -- Orijinal görsel genişliği (px)
    img_h       INTEGER,                       -- Orijinal görsel yüksekliği (px)
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_flyers_week ON flyers (week_id);

-- 3. FLYER_OCR: Vision OCR sonucu cache (flyer başına 1 kayıt)
--    ocr_words: [{text, x0, y0, x1, y1}, ...] (piksel koordinat)
CREATE TABLE IF NOT EXISTS flyer_ocr (
    flyer_id    INTEGER PRIMARY KEY REFERENCES flyers(flyer_id) ON DELETE CASCADE,
    ocr_words   JSONB NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 4. FLYER_CLUSTERS: DBSCAN ile bulunan ürün bölgeleri
--    bbox normalize (0..1), ocr_text = cluster içindeki kelimeler birleşik
CREATE TABLE IF NOT EXISTS flyer_clusters (
    cluster_id  SERIAL PRIMARY KEY,
    flyer_id    INTEGER NOT NULL REFERENCES flyers(flyer_id) ON DELETE CASCADE,
    x0          REAL NOT NULL,                 -- Normalize sol üst X (0..1)
    y0          REAL NOT NULL,
    x1          REAL NOT NULL,                 -- Normalize sağ alt X (0..1)
    y1          REAL NOT NULL,
    ocr_text    TEXT,                          -- Cluster'daki tüm OCR text birleşik
    keys_json   JSONB DEFAULT '{}',            -- Çıkarılan anahtarlar: model, code4, brand...
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_flyer_clusters_flyer ON flyer_clusters (flyer_id);

-- 5. FLYER_MATCHES: Cluster ↔ Excel eşleşmeleri
CREATE TABLE IF NOT EXISTS flyer_matches (
    match_id        SERIAL PRIMARY KEY,
    cluster_id      INTEGER NOT NULL REFERENCES flyer_clusters(cluster_id) ON DELETE CASCADE,
    urun_kodu       TEXT,
    urun_aciklamasi TEXT,
    afis_fiyat      TEXT,
    confidence      REAL DEFAULT 0,
    status          TEXT DEFAULT 'pending'
                    CHECK (status IN ('pending','matched','review','unmatched')),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_flyer_matches_cluster ON flyer_matches (cluster_id);
CREATE INDEX IF NOT EXISTS idx_flyer_matches_status ON flyer_matches (status);

-- 6. WEEKLY_PRODUCTS: Haftalık Excel ürün listesi (hafta başına 1 kez import)
CREATE TABLE IF NOT EXISTS weekly_products (
    id              SERIAL PRIMARY KEY,
    week_id         INTEGER NOT NULL REFERENCES weeks(week_id) ON DELETE CASCADE,
    urun_kodu       TEXT,
    urun_aciklamasi TEXT,
    afis_fiyat      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_weekly_products_week ON weekly_products (week_id);
CREATE INDEX IF NOT EXISTS idx_weekly_products_kod ON weekly_products (urun_kodu);

-- Auto-update triggers
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_flyer_matches_updated ON flyer_matches;
CREATE TRIGGER trg_flyer_matches_updated
    BEFORE UPDATE ON flyer_matches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
