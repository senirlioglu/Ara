-- ============================================================================
-- TÜRKÇE DESTEKLI GELISMIS ARAMA SISTEMI
-- Supabase/PostgreSQL için Full-Text Search + Fuzzy Search
-- ============================================================================

-- 1. EXTENSIONS
-- pg_trgm: Fuzzy search için (benzerlik araması)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- unaccent: Türkçe karakterleri normalize etmek için (opsiyonel)
CREATE EXTENSION IF NOT EXISTS unaccent;


-- 2. TÜRKÇE TEXT SEARCH CONFIGURATION
-- PostgreSQL'de varsayılan Türkçe config yoksa oluştur
DO $$
BEGIN
    -- Türkçe config var mı kontrol et
    IF NOT EXISTS (
        SELECT 1 FROM pg_ts_config WHERE cfgname = 'turkish'
    ) THEN
        -- Simple config'den türet (stemming olmadan)
        CREATE TEXT SEARCH CONFIGURATION turkish (COPY = simple);

        -- Alternatif: Snowball stemmer varsa kullan
        -- CREATE TEXT SEARCH CONFIGURATION turkish (COPY = pg_catalog.simple);
    END IF;
END $$;


-- 3. ÖRNEK PRODUCTS TABLOSU (yoksa oluştur)
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT,
    price DECIMAL(10, 2),
    stock INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);


-- 4. TÜRKÇE KARAKTER NORMALIZE FONKSIYONU
CREATE OR REPLACE FUNCTION normalize_turkish(input_text TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN LOWER(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
            input_text,
            'İ', 'i'), 'I', 'ı'), 'Ğ', 'ğ'), 'Ü', 'ü'),
            'Ş', 'ş'), 'Ö', 'ö'), 'Ç', 'ç'),
            'ı', 'i'), 'ğ', 'g'), 'ü', 'u'),
            'ş', 's'), 'ö', 'o'), 'ç', 'c'
    );
END;
$$ LANGUAGE plpgsql IMMUTABLE;


-- 5. FTS GENERATED COLUMN EKLE
-- Önce mevcut column varsa kaldır
ALTER TABLE products DROP COLUMN IF EXISTS fts;
ALTER TABLE products DROP COLUMN IF EXISTS name_normalized;

-- FTS column ekle (name + description birleşik)
ALTER TABLE products ADD COLUMN fts tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', COALESCE(name, '')), 'A') ||
        setweight(to_tsvector('simple', COALESCE(description, '')), 'B')
    ) STORED;

-- Normalize edilmiş isim (fuzzy search için)
ALTER TABLE products ADD COLUMN name_normalized TEXT
    GENERATED ALWAYS AS (normalize_turkish(COALESCE(name, ''))) STORED;


-- 6. INDEXLER
-- FTS için GIN index
CREATE INDEX IF NOT EXISTS idx_products_fts ON products USING GIN(fts);

-- Fuzzy search için trigram index
CREATE INDEX IF NOT EXISTS idx_products_name_trgm ON products USING GIN(name_normalized gin_trgm_ops);

-- Kategori için index
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);


-- 7. HYBRID SEARCH FUNCTION (RPC)
CREATE OR REPLACE FUNCTION search_products(
    keyword TEXT,
    category_filter TEXT DEFAULT NULL,
    min_price DECIMAL DEFAULT NULL,
    max_price DECIMAL DEFAULT NULL,
    result_limit INTEGER DEFAULT 50,
    fuzzy_threshold FLOAT DEFAULT 0.3
)
RETURNS TABLE (
    id INTEGER,
    name TEXT,
    description TEXT,
    category TEXT,
    price DECIMAL,
    stock INTEGER,
    match_type TEXT,
    rank FLOAT
) AS $$
DECLARE
    normalized_keyword TEXT;
    tsquery_keyword tsquery;
BEGIN
    -- Arama terimini normalize et
    normalized_keyword := normalize_turkish(keyword);

    -- TSQuery oluştur
    tsquery_keyword := plainto_tsquery('simple', keyword);

    RETURN QUERY
    WITH
    -- Full-Text Search sonuçları
    fts_results AS (
        SELECT
            p.id,
            p.name,
            p.description,
            p.category,
            p.price,
            p.stock,
            'exact'::TEXT AS match_type,
            ts_rank(p.fts, tsquery_keyword)::FLOAT AS rank
        FROM products p
        WHERE p.fts @@ tsquery_keyword
            AND (category_filter IS NULL OR p.category = category_filter)
            AND (min_price IS NULL OR p.price >= min_price)
            AND (max_price IS NULL OR p.price <= max_price)
    ),

    -- Fuzzy Search sonuçları (trigram benzerliği)
    fuzzy_results AS (
        SELECT
            p.id,
            p.name,
            p.description,
            p.category,
            p.price,
            p.stock,
            'fuzzy'::TEXT AS match_type,
            similarity(p.name_normalized, normalized_keyword)::FLOAT AS rank
        FROM products p
        WHERE similarity(p.name_normalized, normalized_keyword) >= fuzzy_threshold
            AND p.id NOT IN (SELECT fts.id FROM fts_results fts)  -- FTS'de bulunanları hariç tut
            AND (category_filter IS NULL OR p.category = category_filter)
            AND (min_price IS NULL OR p.price >= min_price)
            AND (max_price IS NULL OR p.price <= max_price)
    ),

    -- Prefix match (başlangıç eşleşmesi)
    prefix_results AS (
        SELECT
            p.id,
            p.name,
            p.description,
            p.category,
            p.price,
            p.stock,
            'prefix'::TEXT AS match_type,
            0.5::FLOAT AS rank
        FROM products p
        WHERE p.name_normalized LIKE (normalized_keyword || '%')
            AND p.id NOT IN (SELECT fts.id FROM fts_results fts)
            AND p.id NOT IN (SELECT fz.id FROM fuzzy_results fz)
            AND (category_filter IS NULL OR p.category = category_filter)
            AND (min_price IS NULL OR p.price >= min_price)
            AND (max_price IS NULL OR p.price <= max_price)
    ),

    -- Tüm sonuçları birleştir
    all_results AS (
        SELECT * FROM fts_results
        UNION ALL
        SELECT * FROM fuzzy_results
        UNION ALL
        SELECT * FROM prefix_results
    )

    -- Sırala ve limit uygula
    SELECT
        ar.id,
        ar.name,
        ar.description,
        ar.category,
        ar.price,
        ar.stock,
        ar.match_type,
        ar.rank
    FROM all_results ar
    ORDER BY
        -- Öncelik: exact > prefix > fuzzy
        CASE ar.match_type
            WHEN 'exact' THEN 1
            WHEN 'prefix' THEN 2
            WHEN 'fuzzy' THEN 3
        END,
        ar.rank DESC
    LIMIT result_limit;

END;
$$ LANGUAGE plpgsql;


-- 8. AUTOCOMPLETE FONKSIYONU (Öneriler için)
CREATE OR REPLACE FUNCTION autocomplete_products(
    partial_keyword TEXT,
    result_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    suggestion TEXT,
    product_count BIGINT
) AS $$
DECLARE
    normalized_partial TEXT;
BEGIN
    normalized_partial := normalize_turkish(partial_keyword);

    RETURN QUERY
    SELECT
        p.name AS suggestion,
        COUNT(*)::BIGINT AS product_count
    FROM products p
    WHERE p.name_normalized LIKE (normalized_partial || '%')
       OR similarity(p.name_normalized, normalized_partial) > 0.2
    GROUP BY p.name
    ORDER BY
        -- Tam eşleşme önce
        CASE WHEN p.name_normalized LIKE (normalized_partial || '%') THEN 0 ELSE 1 END,
        COUNT(*) DESC
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;


-- 9. ÖRNEK VERİ EKLE (Test için)
INSERT INTO products (name, description, category, price, stock) VALUES
    ('Ekmek', 'Taze günlük ekmek', 'Gıda', 5.00, 100),
    ('Ekmeği', 'Kepekli ekmek çeşidi', 'Gıda', 7.50, 50),
    ('Gözlük', 'Güneş gözlüğü', 'Aksesuar', 150.00, 30),
    ('Gözlüğü', 'Optik gözlük', 'Sağlık', 350.00, 20),
    ('Makine', 'Çamaşır makinesi', 'Beyaz Eşya', 8500.00, 15),
    ('Makina', 'Bulaşık makinası', 'Beyaz Eşya', 7500.00, 12),
    ('Bilgisayar', 'Dizüstü bilgisayar', 'Elektronik', 25000.00, 8),
    ('Telefon', 'Akıllı telefon', 'Elektronik', 15000.00, 25),
    ('Buzdolabı', 'No-frost buzdolabı', 'Beyaz Eşya', 18000.00, 10),
    ('Çaydanlık', 'Paslanmaz çelik çaydanlık', 'Mutfak', 450.00, 40),
    ('Şemsiye', 'Otomatik şemsiye', 'Aksesuar', 120.00, 60),
    ('Türkçe Kitap', 'Türkçe öğrenme kitabı', 'Kitap', 85.00, 100),
    ('Öğrenci Çantası', 'Okul çantası', 'Aksesuar', 250.00, 45),
    ('İş Eldiveni', 'Koruyucu eldiven', 'İş Güvenliği', 35.00, 200),
    ('Ütü', 'Buharlı ütü', 'Ev Aletleri', 650.00, 30)
ON CONFLICT DO NOTHING;


-- 10. TEST SORGULARI
-- FTS testi
SELECT * FROM search_products('ekmek');

-- Fuzzy search testi (yazım hatası)
SELECT * FROM search_products('makina');

-- Türkçe karakter testi
SELECT * FROM search_products('gozluk');

-- Autocomplete testi
SELECT * FROM autocomplete_products('bil');


-- ============================================================================
-- NOTLAR:
--
-- 1. PostgreSQL'de varsayılan Türkçe stemmer yoktur. Bu çözüm:
--    - 'simple' config kullanır (stemming yok ama Türkçe karakterler çalışır)
--    - Fuzzy search ile yazım hatalarını yakalar
--    - normalize_turkish() ile ı/i, ğ/g dönüşümlerini yapar
--
-- 2. Daha iyi Türkçe stemming için:
--    - Hunspell sözlük kurulabilir
--    - Veya uygulama katmanında stemming yapılabilir
--
-- 3. Performans için:
--    - GIN indexler kullanılıyor
--    - Trigram indexler fuzzy search hızlandırıyor
--    - LIMIT ile sonuç sayısı sınırlanıyor
-- ============================================================================
