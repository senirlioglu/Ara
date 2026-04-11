# Ara Projesi — Geliştirme Kılavuzu

## Proje Özeti

Mağaza personeli ve müşteriler için ürün arama + afiş yönetim uygulaması.

- **Kullanıcı tarafı**: iyibulur.com → Next.js (Railway'de canlı)
- **Admin tarafı**: Streamlit (ara101.streamlit.app/?admin=true)
- **Backend**: Supabase (PostgreSQL + Storage) — her iki app aynı backend'i kullanır
- **Deploy**:
  - Next.js kullanıcı tarafı: Railway (main branch, Root Directory = `web`)
  - Streamlit admin: Streamlit Cloud (main branch otomatik deploy)

## Mimari

```
iyibulur.com → Next.js (web/)             ← Kullanıcı tarafı
                ├── Ürün arama (autocomplete + barkod tarama)
                ├── Poster viewer (Embla Carousel + hotspot)
                └── GPS ile yakın mağaza sıralama

ara101.streamlit.app/?admin=true          ← Admin tarafı
  ├── Haftalar (oluştur/düzenle/sırala/sil/rename/excel ekle)
  ├── Eşleştir (bbox çiz → ürün eşle → kaydet)
  ├── Poster Yönetimi (başlık/sıra/sil/önizleme)
  └── Analitikler (arama logları)

Supabase (PostgreSQL + Storage)           ← Ortak backend
```

## Next.js (Kullanıcı Tarafı) — `web/`

### Kritik Dosyalar
| Dosya | Rol |
|---|---|
| `web/app/page.tsx` | Ana sayfa (arama + poster + header) |
| `web/app/layout.tsx` | Root layout, metadata, PWA config |
| `web/app/components/SearchBar.tsx` | Arama kutusu, autocomplete, barkod ikonu |
| `web/app/components/ProductCard.tsx` | Ürün kartı, fiyat, mağaza listesi, sıralama |
| `web/app/components/PosterViewer.tsx` | Embla Carousel poster slider + hotspot |
| `web/app/components/BarcodeScanner.tsx` | Kamera barkod tarama (html5-qrcode) |
| `web/app/components/LocationProvider.tsx` | GPS context + localStorage cache |
| `web/app/components/LocationBanner.tsx` | Konum izni banner'ı |
| `web/lib/supabase.ts` | Supabase client (lazy init, build-safe) |
| `web/lib/api.ts` | Tüm Supabase sorguları (arama, poster, barkod, log) |
| `web/lib/turkish.ts` | SQL `normalize_tr_search` ile birebir normalizasyon |
| `web/lib/distance.ts` | Haversine mesafe hesaplama |
| `web/lib/types.ts` | TypeScript tip tanımları |
| `web/public/oneri_listesi.json` | Autocomplete için ürün listesi (pipeline üretir) |
| `web/public/manifest.json` | PWA manifest |
| `web/public/sw.js` | Service worker (network-first cache) |
| `web/railway.toml` | Railway Nixpacks config |

### Kararlar (değiştirmeyin)
1. **Embla Carousel** — poster slider için custom swipe yerine. Ghost image sorunu yok, momentum, snap. Geri dönüştürmeyin.
2. **LocationProvider** — konum izni önce bizim banner'da sorulur (yanlış "Hayır" önleme), sonra tarayıcı izni çıkar.
3. **Lazy Supabase init** — `lib/supabase.ts` proxy ile runtime'da client oluşturur (build hata vermesin diye).
4. **oneri_listesi.json pipeline** — `urun_master_pipeline.py` `web/public/oneri_listesi.json`'ı günceller. Ayrı kopya tutmayın.
5. **Barkod akışı** — Input → `lookupBarcode()` → `urun_barkod` tablosu → `urun_kod` → `searchProducts()`. 8-14 digit giriş önce barkod olarak denenir, olmazsa ürün kodu fallback.

### Env Variables (Railway)
- `NEXT_PUBLIC_SUPABASE_URL` — Supabase project URL
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` — Supabase anon key (aynı Streamlit'le)

## Streamlit (Admin Tarafı) — kök dizin

### Kritik Dosyalar
| Dosya | Rol |
|---|---|
| `urun_ara_app.py` | Ana Streamlit uygulaması (admin + legacy kullanıcı) |
| `storage.py` | Supabase CRUD (mappings, poster pages, weeks, products) |
| `mapping_ui/search.py` | Client-side ürün arama (pre-indexed, Turkish normalization) |
| `components/bbox_canvas/` | Custom Streamlit component — poster üzerinde kutu çizme |
| `components/poster_viewer/` | Custom Streamlit component — admin önizleme |
| `urun_master_pipeline.py` | Günlük ürün master üretimi (GitHub Actions ile otomatik) |

### Admin Panel Performans Mimarisi

Admin paneli `st.tabs()` yerine **conditional router** kullanır (st.segmented_control). Her rerun'da sadece aktif sekme çalışır. Bu en kritik performans kararıdır — geri dönüştürmeyin.

### Performans Kararları (değiştirmeyin)
1. **Conditional router** (`admin_panel()` içinde) — `st.tabs()` kullanmayın, tüm sekmeleri çalıştırır
2. **Pre-indexed search** — `build_search_index()` hafta yüklendiğinde çağrılır, `search_products()` pre-computed `_norm_text`/`_norm_tokens` kullanır
3. **Bulk DB operations** — `_mt_flush_to_supabase()` toplu insert/delete/update yapar, row-by-row değil
4. **Poster metadata vs full** — Admin form'ları `get_poster_pages_meta()` kullanır (image download yok), sadece önizleme `get_poster_pages()` kullanır
5. **Analytics cache** — `@st.cache_data(ttl=300)` ile 5 dk cache
6. **Stable identity** — Tüm selectbox/radio seçimleri positional index yerine stable identity kullanır (urun_kod, mapping_id)

### Widget Sayısı Kuralları
- Remaining products: `st.radio` (1 widget, görünür liste) + pagination (15 item window)
- Search results: `st.radio` (1 widget) + tek action button
- Saved mappings: `st.selectbox` by mapping_id + edit form (expander içinde)
- Inline per-row butonlar kullanmayın — widget patlaması yapar

### Session State Anahtar Kuralları
| Key | Tip | Açıklama |
|---|---|---|
| `mt_queue_kod` | str | Seçili ürün kodu (stable identity, index değil) |
| `mt_pending_mappings` | list | Flush edilmemiş yeni mapping'ler |
| `mt_pending_deletes` | list | Flush edilmemiş silme ID'leri |
| `mt_pending_updates` | dict | Flush edilmemiş güncelleme {mapping_id: fields} |
| `mt_dirty` | bool | Kaydedilmemiş değişiklik var mı |
| `mt_db_cache` | dict | Sayfa bazlı mapping cache (page_key → mappings) |
| `mt_db_mapped_codes` | set | DB'den yüklenmiş mapped kodlar |
| `_pv_cache_{week_id}` | list | Poster pages full cache (görseller dahil) |
| `admin_section` | str | Aktif admin sekmesi (conditional router) |

## Supabase Tabloları

| Tablo | İçerik |
|---|---|
| `stok_gunluk` | Günlük stok verisi (ürün kodu, ad, fiyat, mağaza, adet, lat/lon) |
| `poster_weeks` | Hafta metadata (week_id, week_name, status, sort_order) |
| `poster_pages` | Afiş sayfaları metadata (image_path → Supabase Storage) |
| `week_products` | Haftalık ürün listesi (Excel'den yüklenen, `afis_fiyat` dahil) |
| `mappings` | Bbox-ürün eşleştirmeleri (x0,y0,x1,y1 + urun_kodu) |
| `urun_barkod` | Barkod → ürün kod eşleştirmesi (kullanıcı tarafı barkod araması) |
| `arama_log` | Arama analitikleri |

## Supabase Storage Bucket'ları

| Bucket | İçerik |
|---|---|
| `poster-images` | Poster sayfa görselleri ({week_id}/{filename}_p{no}.jpg) |
| `product-images` | Ürün görselleri (bbox'tan kırpılmış, {urun_kodu}.jpg) |

## Ürün Görseli Kırpma
- Flush sırasında her yeni mapping'in bbox bölgesi otomatik kırpılıp `product-images/{urun_kodu}.jpg` olarak yüklenir
- Poster Yönetimi sekmesinde "Görselleri Oluştur" butonu ile mevcut mapping'ler için toplu backfill
- İlgili fonksiyonlar: `storage.py` → `crop_and_upload_product_image()`, `backfill_product_images()`

## Opsiyonel Supabase RPC

Hafta istatistikleri için tek sorguda count almak için (yoksa fallback HEAD count kullanılır):

```sql
CREATE OR REPLACE FUNCTION get_week_counts()
RETURNS TABLE(week_id TEXT, page_count BIGINT, mapping_count BIGINT, product_count BIGINT)
LANGUAGE sql STABLE AS $$
  SELECT pw.week_id,
    COALESCE(pp.cnt, 0), COALESCE(mp.cnt, 0), COALESCE(wp.cnt, 0)
  FROM poster_weeks pw
  LEFT JOIN (SELECT week_id, COUNT(*) cnt FROM poster_pages GROUP BY week_id) pp USING (week_id)
  LEFT JOIN (SELECT week_id, COUNT(*) cnt FROM mappings GROUP BY week_id) mp USING (week_id)
  LEFT JOIN (SELECT week_id, COUNT(*) cnt FROM week_products GROUP BY week_id) wp USING (week_id)
$$;
```

## PWA / Kiosk Notları
- ~1000 kullanıcı iyibulur.com'u ana ekrana eklemiş
- Domain (iyibulur.com) değişmediği sürece kullanıcıların yeniden yükleme yapması gerekmez
- Next.js kendi PWA manifest + service worker'ını sağlar (web/public/)
- Kiosk (22" Android ekran + USB barkod okuyucu) aynı URL'i kullanabilir
- Barkod okuyucu klavye input olarak çalışır → arama kutusuna auto-focus gerekir

## Deploy Yapılandırması

### Railway — Next.js (Kullanıcı)
- **Branch**: `main`
- **Root Directory**: `web`
- **Builder**: Nixpacks (via `web/railway.toml`)
- **Custom Domain**: `iyibulur.com` (veya alternatif)
- **Env**: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`

### Streamlit Cloud — Admin
- **Branch**: `main`
- **Root**: kök dizin (`urun_ara_app.py`)
- **Env**: `SUPABASE_URL`, `SUPABASE_KEY`, `ADMIN_PASSWORD`

### Streamlit Railway (Eski)
- Root `railway.toml` Streamlit Dockerfile config'i içerir (geri uyumluluk)
- Bu servis opsiyonel — Streamlit Cloud zaten deploy ediyor

## Geliştirme Kuralları

- `main` branch'e doğrudan push yapmayın — PR ile merge edin
- Streamlit Cloud `main` branch'i otomatik deploy eder
- Railway `main` branch'ini otomatik deploy eder (web/ altını)
- GitHub Actions her gün 10:30 TR saatinde `urun_master_pipeline.py` çalıştırır → `data/oneri_listesi.json` ve `web/public/oneri_listesi.json` üretir
- Admin şifresi: `ADMIN_PASSWORD` environment variable / Streamlit secrets
- Supabase credentials:
  - Streamlit: `SUPABASE_URL`, `SUPABASE_KEY`
  - Next.js: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
