# Ara Projesi — Geliştirme Kılavuzu

## Proje Özeti

Mağaza personeli ve müşteriler için ürün arama + afiş yönetim uygulaması.

- **Kullanıcı tarafı**: iyibulur.com → index.html (PWA wrapper) → iframe ile Streamlit app
- **Admin tarafı**: Streamlit (ara101.streamlit.app/?admin=true)
- **Backend**: Supabase (PostgreSQL + Storage)
- **Deploy**: Streamlit Cloud (main branch otomatik deploy)

## Mimari

```
iyibulur.com (index.html — PWA wrapper)
  └── iframe → Ara101.streamlit.app
        ├── Kullanıcı: Ürün arama (stok_gunluk tablosu)
        ├── Kullanıcı: Poster/afiş görüntüleyici
        └── Admin: /?admin=true
              ├── Haftalar (hafta oluştur/düzenle/sırala/sil)
              ├── Eşleştir (bbox çiz → ürün eşle → kaydet)
              ├── Poster Yönetimi (başlık/sıra/sil/önizleme)
              └── Analitikler (arama logları)
```

## Kritik Dosyalar

| Dosya | Rol |
|---|---|
| `urun_ara_app.py` | Ana Streamlit uygulaması (kullanıcı + admin) |
| `storage.py` | Supabase CRUD (mappings, poster pages, weeks, products) |
| `mapping_ui/search.py` | Client-side ürün arama (pre-indexed, Turkish normalization) |
| `components/bbox_canvas/` | Custom Streamlit component — poster üzerinde kutu çizme |
| `components/poster_viewer/` | Custom Streamlit component — poster görüntüleyici |
| `urun_master_pipeline.py` | Günlük ürün master üretimi (GitHub Actions ile otomatik) |
| `index.html` | PWA wrapper (iyibulur.com'da serve edilir) |
| `manifest.json` | PWA manifest |
| `static/sw.js` | Service worker |

## Supabase Tabloları

| Tablo | İçerik |
|---|---|
| `stok_gunluk` | Günlük stok verisi (ürün kodu, ad, fiyat, mağaza, adet) |
| `poster_weeks` | Hafta metadata (week_id, week_name, status, sort_order) |
| `poster_pages` | Afiş sayfaları metadata (image_path → Supabase Storage) |
| `week_products` | Haftalık ürün listesi (Excel'den yüklenen) |
| `mappings` | Bbox-ürün eşleştirmeleri (x0,y0,x1,y1 + urun_kodu) |
| `arama_log` | Arama analitikleri |

## Supabase Storage Bucket'ları

| Bucket | İçerik |
|---|---|
| `poster-images` | Poster sayfa görselleri ({week_id}/{filename}_p{no}.jpg) |
| `product-images` | Ürün görselleri (bbox'tan kırpılmış, {urun_kodu}.jpg) |

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

## Admin Panel Performans Mimarisi

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

## Ürün Görseli Kırpma

- Flush sırasında her yeni mapping'in bbox bölgesi otomatik kırpılıp `product-images/{urun_kodu}.jpg` olarak yüklenir
- Poster Yönetimi sekmesinde "Görselleri Oluştur" butonu ile mevcut mapping'ler için toplu backfill
- İlgili fonksiyonlar: `storage.py` → `crop_and_upload_product_image()`, `backfill_product_images()`

## Session State Anahtar Kuralları

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

## PWA / Kiosk Notları

- ~1000 kullanıcı iyibulur.com'u ana ekrana eklemiş
- Domain (iyibulur.com) değişmediği sürece kullanıcıların yeniden yükleme yapması gerekmez
- iframe src değiştirilse bile PWA wrapper aynı kalır
- Kiosk (22" Android ekran + USB barkod okuyucu) aynı URL'i kullanabilir
- Barkod okuyucu klavye input olarak çalışır → arama kutusuna auto-focus gerekir

## Planlanan Özellikler

1. **Barkod ile arama** — `urun_barkod` tablosu yüklenecek (urun_kod, urun_ad, barkod), hem telefon kamera hem kiosk USB okuyucu desteği
2. **Kullanıcı tarafı TypeScript'e geçiş** — Next.js + Tailwind + Supabase JS SDK. Admin Streamlit'te kalır. Aynı Supabase backend.
3. **Deploy değişikliği** — Railway veya Vercel değerlendirilecek

## Geliştirme Kuralları

- `main` branch'e doğrudan push yapmayın — PR ile merge edin
- Streamlit Cloud `main` branch'i otomatik deploy eder
- GitHub Actions her gün 10:30 TR saatinde `urun_master_pipeline.py` çalıştırır
- Admin şifresi: `ADMIN_PASSWORD` environment variable / Streamlit secrets
- Supabase credentials: `SUPABASE_URL`, `SUPABASE_KEY`
