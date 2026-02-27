-- ============================================================================
-- POSTER HOTSPOT FEATURE - DATABASE SCHEMA
-- Haftalık afiş/poster üzerinden ürün arama özelliği
-- ============================================================================

-- 1. POSTERS: Her hafta yüklenen afiş PDF'leri
CREATE TABLE IF NOT EXISTS posters (
    poster_id   SERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    week_date   DATE NOT NULL,                  -- Haftanın başlangıç tarihi
    pdf_url     TEXT,                            -- Supabase Storage veya harici URL
    page_count  INTEGER DEFAULT 1,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_posters_week ON posters (week_date DESC);


-- 2. POSTER_ITEMS: Excel'den okunan afiş ürünleri
CREATE TABLE IF NOT EXISTS poster_items (
    id                SERIAL PRIMARY KEY,
    poster_id         INTEGER NOT NULL REFERENCES posters(poster_id) ON DELETE CASCADE,
    page_no           INTEGER,                   -- Sayfa numarası (1-based, NULL = bilinmiyor)
    urun_kodu         TEXT,                       -- Excel: ÜRÜN KODU
    urun_aciklamasi   TEXT,                       -- Excel: ÜRÜN AÇIKLAMASI
    afis_fiyat        TEXT,                       -- Excel: AFIS_FIYAT (text: "42.999 TL" gibi)
    -- Eşleşme sonuçları
    match_sku_id      TEXT,                       -- Eşleşen ürün kodu (stok_gunluk.urun_kod)
    search_term       TEXT,                       -- Arama tetikleyici (kod veya model)
    match_confidence  REAL DEFAULT 0,             -- 0.0 - 1.0
    status            TEXT DEFAULT 'pending'      -- pending / matched / review / unmatched
                      CHECK (status IN ('pending','matched','review','unmatched')),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_poster_items_poster ON poster_items (poster_id);
CREATE INDEX IF NOT EXISTS idx_poster_items_status ON poster_items (status);
CREATE INDEX IF NOT EXISTS idx_poster_items_urun_kodu ON poster_items (urun_kodu);


-- 3. POSTER_HOTSPOTS: PDF üzerindeki tıklanabilir alanlar (normalize 0..1)
CREATE TABLE IF NOT EXISTS poster_hotspots (
    id              SERIAL PRIMARY KEY,
    poster_item_id  INTEGER NOT NULL REFERENCES poster_items(id) ON DELETE CASCADE,
    page_no         INTEGER NOT NULL,            -- 1-based sayfa numarası
    x0              REAL NOT NULL,                -- Sol üst X (0.0 - 1.0)
    y0              REAL NOT NULL,                -- Sol üst Y (0.0 - 1.0)
    x1              REAL NOT NULL,                -- Sağ alt X (0.0 - 1.0)
    y1              REAL NOT NULL,                -- Sağ alt Y (0.0 - 1.0)
    source          TEXT DEFAULT 'auto'           -- auto / manual
                    CHECK (source IN ('auto','manual')),
    updated_by      TEXT,                         -- admin kullanıcı adı
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_poster_hotspots_item ON poster_hotspots (poster_item_id);
CREATE INDEX IF NOT EXISTS idx_poster_hotspots_page ON poster_hotspots (poster_item_id, page_no);


-- 4. HELPER: Trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_poster_items_updated ON poster_items;
CREATE TRIGGER trg_poster_items_updated
    BEFORE UPDATE ON poster_items
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trg_poster_hotspots_updated ON poster_hotspots;
CREATE TRIGGER trg_poster_hotspots_updated
    BEFORE UPDATE ON poster_hotspots
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
