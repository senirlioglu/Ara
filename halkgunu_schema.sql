-- ============================================================================
-- HALK GÜNÜ — DATABASE SCHEMA
-- Belirli tarihlerde belirli mağazalarda belirli ürünlerin indirimli satıldığı
-- etkinlikler için. Frontend halkgunu.net (Vercel/Next.js), admin Ara
-- Streamlit panelinde "Halk Günü" sekmesi olarak yönetilir.
--
-- Aynı Supabase projesini Ara ile paylaşır. Mağaza bilgileri `magazalar`
-- tablosundan, ürün resimleri `product-images` storage bucket'ından gelir.
-- ============================================================================

-- 1. HALKGUNU_EVENTS: Etkinlikler (Ara'daki poster_weeks benzeri)
CREATE TABLE IF NOT EXISTS halkgunu_events (
    event_id    TEXT PRIMARY KEY,                       -- Örn: "2026-05-15" veya "halkgunu_2026_05_15"
    event_name  TEXT NOT NULL,                          -- Görünen ad: "15 Mayıs 2026 Halk Günü"
    event_date  DATE NOT NULL,                          -- Etkinlik tarihi
    status      TEXT DEFAULT 'draft'                    -- draft / active / archived
                CHECK (status IN ('draft','active','archived')),
    sort_order  INTEGER DEFAULT 0,                      -- Frontend tarih sekmelerinde sıralama
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_halkgunu_events_date
    ON halkgunu_events (event_date DESC);
CREATE INDEX IF NOT EXISTS idx_halkgunu_events_sort
    ON halkgunu_events (sort_order, event_date DESC);


-- 2. HALKGUNU_PRODUCTS: Excel'den yüklenen indirimli ürün listesi
-- Aynı (event, ürün, mağaza) kombinasyonu birden fazla satıra bölünmez (UNIQUE).
-- magaza_ad denormalize tutulmaz; magazalar tablosundan join ile alınır.
CREATE TABLE IF NOT EXISTS halkgunu_products (
    id              BIGSERIAL PRIMARY KEY,
    event_id        TEXT NOT NULL REFERENCES halkgunu_events(event_id) ON DELETE CASCADE,
    urun_kod        TEXT NOT NULL,                      -- Excel: ÜRÜN KODU
    urun_ad         TEXT,                                -- Excel: ÜRÜN ADI (referans/snapshot)
    magaza_kod      TEXT NOT NULL,                      -- magazalar.magaza_kod ile eşleşir
    normal_fiyat    NUMERIC(12, 2),                     -- Excel: NORMAL FİYAT
    indirimli_fiyat NUMERIC(12, 2),                     -- Excel: İNDİRİMLİ FİYAT
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (event_id, urun_kod, magaza_kod)
);

CREATE INDEX IF NOT EXISTS idx_halkgunu_products_event
    ON halkgunu_products (event_id);
CREATE INDEX IF NOT EXISTS idx_halkgunu_products_event_urun
    ON halkgunu_products (event_id, urun_kod);
CREATE INDEX IF NOT EXISTS idx_halkgunu_products_event_magaza
    ON halkgunu_products (event_id, magaza_kod);


-- 3. HALKGUNU_PAGES: Afiş sayfaları (Ara'daki poster_pages benzeri)
-- Görseller `poster-images` bucket'ında {event_id}/{filename}_p{no}.jpg yolunda.
CREATE TABLE IF NOT EXISTS halkgunu_pages (
    id              BIGSERIAL PRIMARY KEY,
    event_id        TEXT NOT NULL REFERENCES halkgunu_events(event_id) ON DELETE CASCADE,
    flyer_filename  TEXT NOT NULL,
    page_no         INTEGER NOT NULL,
    image_path      TEXT NOT NULL,                       -- Storage yolu
    title           TEXT DEFAULT '',
    sort_order      INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (event_id, flyer_filename, page_no)
);

CREATE INDEX IF NOT EXISTS idx_halkgunu_pages_event
    ON halkgunu_pages (event_id, sort_order, flyer_filename, page_no);


-- 4. HALKGUNU_MAPPINGS: Afiş üzerindeki bbox-ürün eşleştirmeleri
-- Ara'daki `mappings` tablosunun aynı şekli, ek olarak event_id kolonuyla.
CREATE TABLE IF NOT EXISTS halkgunu_mappings (
    mapping_id      BIGSERIAL PRIMARY KEY,
    event_id        TEXT NOT NULL REFERENCES halkgunu_events(event_id) ON DELETE CASCADE,
    flyer_filename  TEXT NOT NULL,
    page_no         INTEGER NOT NULL,
    x0              REAL NOT NULL,                       -- 0.0 - 1.0
    y0              REAL NOT NULL,
    x1              REAL NOT NULL,
    y1              REAL NOT NULL,
    urun_kodu       TEXT,                                -- Eşleşen ürün
    urun_aciklamasi TEXT,
    afis_fiyat      TEXT,                                -- Görüntüleme amaçlı (text)
    ocr_text        TEXT,
    source          TEXT DEFAULT 'manual'                -- manual / auto / suggested
                    CHECK (source IN ('manual','auto','suggested')),
    status          TEXT DEFAULT 'matched'               -- matched / pending / review
                    CHECK (status IN ('matched','pending','review','unmatched')),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_halkgunu_mappings_event
    ON halkgunu_mappings (event_id);
CREATE INDEX IF NOT EXISTS idx_halkgunu_mappings_page
    ON halkgunu_mappings (event_id, flyer_filename, page_no);
CREATE INDEX IF NOT EXISTS idx_halkgunu_mappings_urun
    ON halkgunu_mappings (event_id, urun_kodu);


-- 5. updated_at trigger (poster_schema.sql ile aynı helper, idempotent)
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_halkgunu_events_updated ON halkgunu_events;
CREATE TRIGGER trg_halkgunu_events_updated
    BEFORE UPDATE ON halkgunu_events
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- 6. OPSIYONEL RPC: Etkinlik başına sayım (Ara'daki get_week_counts benzeri)
-- Admin panelinde her etkinliğin yanında "X ürün, Y sayfa, Z mapping" göstermek için.
CREATE OR REPLACE FUNCTION get_halkgunu_counts()
RETURNS TABLE(
    event_id      TEXT,
    page_count    BIGINT,
    mapping_count BIGINT,
    product_count BIGINT,
    store_count   BIGINT
)
LANGUAGE sql STABLE AS $$
    SELECT he.event_id,
        COALESCE(pp.cnt, 0) AS page_count,
        COALESCE(mp.cnt, 0) AS mapping_count,
        COALESCE(pr.cnt, 0) AS product_count,
        COALESCE(st.cnt, 0) AS store_count
    FROM halkgunu_events he
    LEFT JOIN (
        SELECT event_id, COUNT(*) cnt FROM halkgunu_pages GROUP BY event_id
    ) pp USING (event_id)
    LEFT JOIN (
        SELECT event_id, COUNT(*) cnt FROM halkgunu_mappings GROUP BY event_id
    ) mp USING (event_id)
    LEFT JOIN (
        SELECT event_id, COUNT(*) cnt FROM halkgunu_products GROUP BY event_id
    ) pr USING (event_id)
    LEFT JOIN (
        SELECT event_id, COUNT(DISTINCT magaza_kod) cnt
        FROM halkgunu_products GROUP BY event_id
    ) st USING (event_id);
$$;


-- 7. OPSIYONEL RPC: Bir ürünün belirli etkinlikteki indirimli mağaza listesi
-- halkgunu.net frontend'inde ürüne tıklayınca açılan mağaza popup'ı için.
-- magazalar (konum, adres) ve stok_gunluk (canlı stok) ile join'lenir.
CREATE OR REPLACE FUNCTION get_halkgunu_product_stores(
    p_event_id TEXT,
    p_urun_kod TEXT
)
RETURNS TABLE(
    magaza_kod      TEXT,
    magaza_adi      TEXT,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    adres           TEXT,
    normal_fiyat    NUMERIC,
    indirimli_fiyat NUMERIC,
    stok_adet       INTEGER
)
LANGUAGE sql STABLE AS $$
    SELECT
        hp.magaza_kod,
        m.magaza_adi,
        m.latitude,
        m.longitude,
        m.adres,
        hp.normal_fiyat,
        hp.indirimli_fiyat,
        COALESCE(sg.stok_adet, 0)::INTEGER AS stok_adet
    FROM halkgunu_products hp
    LEFT JOIN magazalar m ON m.magaza_kod = hp.magaza_kod
    LEFT JOIN stok_gunluk sg
           ON sg.magaza_kod = hp.magaza_kod
          AND sg.urun_kod   = hp.urun_kod
    WHERE hp.event_id = p_event_id
      AND hp.urun_kod = p_urun_kod
    ORDER BY indirimli_fiyat NULLS LAST, magaza_adi;
$$;


-- ============================================================================
-- STORAGE BUCKETS (manuel olarak Supabase dashboard'dan da oluşturulabilir)
-- ============================================================================
-- poster-images   : Afiş sayfaları (Ara ile paylaşılır, yol prefix'i event_id ile ayrılır)
-- product-images  : Ürün resimleri (Ara ile paylaşılır, urun_kod ortak anahtar)
--
-- Halk Günü için ek bucket gerekmez. Liste modunda eksik ürün resimleri admin'den
-- yüklendiğinde aynı `product-images/{urun_kod}.jpg` yoluna yazılır.
-- ============================================================================
