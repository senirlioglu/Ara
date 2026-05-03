# Halk Günü — Hand-off Dokümanı

Bu doküman yeni Claude Code session'ı için kapsamlı bağlam sağlar. Halk Günü
özelliği `senirlioglu/Ara` ile `senirlioglu/halkgunu` arasında bölünmüş bir
projedir; backend Ara'da, frontend halkgunu'da. Aynı Supabase backend paylaşılır.

---

## TL;DR

- **Ne**: `halkgunu.net` — belirli tarihlerde belirli mağazalarda indirimli
  ürünleri gösteren ayrı bir kullanıcı sitesi. Aynı Supabase, aynı stok
  altyapısı (Ara'nın `magazalar` ve `stok_gunluk` tablolarını okur).
- **Mimari**:
  - **Backend + Admin**: `senirlioglu/Ara` (Streamlit) — `Halk Günü` admin sekmesi
    yeni eklendi
  - **Frontend**: `senirlioglu/halkgunu` (Next.js 14 + TypeScript + Tailwind)
    — Vercel'de deploy edilecek, `halkgunu.net` domain'ine bağlanacak
- **Veri**: 4 yeni tablo + 2 RPC, `poster-images` ve `product-images`
  bucket'larını Ara ile paylaşır (poster yolları `halkgunu/` prefix'i ile
  namespace edilir)
- **Açık iş**: halkgunu repo'sunda `src/lib/*.ts` 4 dosyası eksik (Ara'nın
  .gitignore'ı yüzünden ilk commit'te silindi). Vercel build bu yüzden fail
  oluyor. Detay aşağıda "Bilinen Sorunlar"da.

---

## Sistem Mimarisi

```
┌────────────────────────┐         ┌────────────────────────┐
│  iyibulur.com          │         │  halkgunu.net          │
│  (PWA wrapper)         │         │  (Next.js / Vercel)    │
│   └─ iframe →          │         │   └─ Next.js App       │
│      ara101.streamlit  │         │      Router            │
└──────────┬─────────────┘         └──────────┬─────────────┘
           │                                   │
           └─────────────┬─────────────────────┘
                         ▼
            ┌────────────────────────┐
            │  Supabase (paylaşılır) │
            │  • PostgreSQL          │
            │  • Storage (2 bucket)  │
            │  • RPC                 │
            └────────────────────────┘
                         ▲
            ┌────────────┴───────────┐
            │  Ara — Streamlit       │
            │  (admin + kullanıcı)   │
            │  ara101.streamlit.app  │
            │  /?admin=true          │
            └────────────────────────┘
```

- **Ara**: Streamlit Cloud'da (`main` branch otomatik deploy). Admin paneli
  `Halk Günü` sekmesi içerir — etkinlik, afiş, ürün listesi, bbox eşleştirme.
- **halkgunu.net**: Vercel'de (`main` branch otomatik deploy). Yalnızca
  kullanıcı tarafı (read-only).
- **Supabase**: Aynı proje, aynı `SUPABASE_URL` / `SUPABASE_KEY`. Ara'nın
  RLS politikaları varsa halkgunu da onları kullanır (anon key okuma).

---

## Supabase Şeması

### Mevcut (Ara'dan paylaşılan)

| Tablo | Kullanım |
|---|---|
| `magazalar` | `magaza_kod` PK, `magaza_adi`, `latitude`, `longitude`, `adres` — mağaza listesi (StoreModal join'i bunu kullanır) |
| `stok_gunluk` | Günlük stok — Halk Günü mağaza listesinde canlı stok göstermek için join'lenir |

### Yeni (halkgunu_schema.sql ile eklendi)

```sql
-- 1) halkgunu_events
event_id    TEXT PRIMARY KEY            -- "halkgunu_2026_05_15" gibi
event_name  TEXT NOT NULL                -- "15 Mayıs 2026 Halk Günü"
event_date  DATE NOT NULL
status      TEXT  -- 'draft' | 'active' | 'archived'
sort_order  INTEGER DEFAULT 0
created_at  TIMESTAMPTZ
updated_at  TIMESTAMPTZ                  -- trigger ile otomatik

-- 2) halkgunu_products  (Excel'den yüklenen indirim listesi)
id              BIGSERIAL PK
event_id        FK halkgunu_events ON DELETE CASCADE
urun_kod        TEXT NOT NULL
urun_ad         TEXT
magaza_kod      TEXT NOT NULL  -- magazalar.magaza_kod ile eşleşir
normal_fiyat    NUMERIC(12,2)
indirimli_fiyat NUMERIC(12,2)
UNIQUE (event_id, urun_kod, magaza_kod)

-- 3) halkgunu_pages  (afiş sayfaları)
id              BIGSERIAL PK
event_id        FK CASCADE
flyer_filename  TEXT
page_no         INTEGER
image_path      TEXT  -- "halkgunu/{event_id}/{filename}_p{n}.jpg"
title           TEXT
sort_order      INTEGER
UNIQUE (event_id, flyer_filename, page_no)

-- 4) halkgunu_mappings  (bbox eşleştirmeleri)
mapping_id      BIGSERIAL PK
event_id        FK CASCADE
flyer_filename, page_no
x0, y0, x1, y1  REAL  -- 0.0–1.0 normalize
urun_kodu       TEXT
urun_aciklamasi TEXT
afis_fiyat      TEXT
ocr_text        TEXT
source          'manual' | 'auto' | 'suggested'
status          'matched' | 'pending' | 'review' | 'unmatched'
```

### RPC

```sql
get_halkgunu_counts()
-- Dönüş: (event_id, page_count, mapping_count, product_count, store_count)
-- Admin'in etkinlik listesinde rozet sayılarını tek sorguda almak için.

get_halkgunu_product_stores(p_event_id, p_urun_kod)
-- Dönüş: (magaza_kod, magaza_adi, latitude, longitude, adres,
--          normal_fiyat, indirimli_fiyat, stok_adet)
-- Frontend StoreModal'in kullandığı join. magazalar + stok_gunluk birleşimi.
```

### Storage Bucket'ları

| Bucket | İçerik |
|---|---|
| `poster-images` | Hem Ara'nın poster_pages hem halkgunu_pages tarafından kullanılır. Path collision'dan kaçınmak için Halk Günü dosyaları `halkgunu/{event_id}/...` prefix'i altında |
| `product-images` | Tamamen paylaşılır. `{urun_kod}.jpg` ortak anahtar — Ara'nın bbox kırpılmış görselleri ile Halk Günü Excel/manuel yüklemeleri aynı bucket'ı kullanır |

---

## Repo Yapısı

### `senirlioglu/Ara` (Streamlit + admin)

Halk Günü için eklenen dosyalar:

```
Ara/
├─ halkgunu_schema.sql       # SQL migration (yeni tablolar + RPC)
├─ halkgunu_storage.py        # Halk Günü CRUD modülü
├─ urun_ara_app.py            # ~1100 satır eklendi (admin Halk Günü sekmesi)
├─ HALKGUNU_HANDOFF.md        # bu doküman
└─ CLAUDE.md                  # Ana proje rehberi (değişmedi)
```

### `senirlioglu/halkgunu` (Next.js)

```
halkgunu/
├─ package.json               # next 14.2.13, react 18, supabase-js, tailwind
├─ tsconfig.json              # paths: @/* → src/*
├─ next.config.js             # Supabase storage remote pattern whitelist
├─ tailwind.config.ts         # Brand renkler #667eea → #764ba2 (Ara ile aynı)
├─ postcss.config.js
├─ .env.local.example
├─ .gitignore
├─ README.md
└─ src/
   ├─ app/
   │  ├─ layout.tsx           # RootLayout (lang=tr, theme-color)
   │  ├─ page.tsx             # Orchestrator: tabs → mode → view → modal
   │  └─ globals.css          # Tailwind + .store-card class
   ├─ components/
   │  ├─ EventTabs.tsx        # Yatay tarih sekmeleri
   │  ├─ ModeToggle.tsx       # Liste/Afiş switcher
   │  ├─ ListView.tsx         # Search + grid
   │  ├─ ProductCard.tsx      # Kart (resim, kod, ad, indirim%)
   │  ├─ PosterView.tsx       # Thumbnail + ana resim + bbox overlay
   │  └─ StoreModal.tsx       # Mağaza listesi popup'ı
   └─ lib/                    # ⚠️ EKSİK — bkz "Bilinen Sorunlar"
      ├─ supabase.ts          # Supabase client + bucket URL helper'ları
      ├─ api.ts               # Tüm DB sorguları
      ├─ types.ts             # TypeScript tipleri
      └─ format.ts            # TR currency/date + indirim%
```

---

## Kod Rehberi — Ara Tarafı

### `halkgunu_schema.sql`
Tek seferde Supabase SQL editöründe çalıştırılır. Idempotent (`IF NOT EXISTS`).

### `halkgunu_storage.py`
Ara'nın `storage.py` modülünü import eder ve onu tamamlar:
- `_get_client`, `_safe_path_segment`, `crop_and_upload_product_image`,
  `upload_product_image`, `get_product_image_url` Ara'dan paylaşılır
- Poster yolları `halkgunu/` prefix'i ile yazılır (`_hg_image_path`)
- `_safe_decimal`: Excel'in "42.999,90" / "42,999.90" formatlarını tolere eder

Public fonksiyonlar (43 adet):
- **Events**: `save_event`, `get_event`, `list_events_with_meta`, `list_all_events`,
  `update_event_status`, `update_event_sort_order`, `delete_event`,
  `get_max_event_sort_order`
- **Pages**: `save_page`, `save_pages_bulk`, `get_event_pages` (resim dahil),
  `get_event_pages_meta` (resimsiz — admin liste için), `update_page`,
  `delete_page`, `get_max_page_sort_order`
- **Mappings**: `save_mapping`, `list_page_mappings`, `list_event_mappings`,
  `update_mapping`, `delete_mapping`, `save_mappings_bulk`,
  `delete_mappings_bulk`, `update_mappings_bulk`
- **Products**: `save_event_products` (replace strategy), `get_event_products`,
  `get_event_product_codes`, `get_event_product_summary` (distinct + min/max
  fiyat), `get_product_stores` (RPC + fallback)
- **Images**: `upload_event_product_image`, `get_event_product_image_url`,
  `list_event_product_image_status`, `backfill_event_product_images`

### `urun_ara_app.py` (admin paneli)

Conditional router'a yeni sekme eklendi (st.tabs() KULLANMIYOR — performans):

```python
_ADMIN_SECTIONS = ["Haftalar", "Eşleştir", "Poster Yönetimi", "Halk Günü", "Analitikler"]
```

`Halk Günü` sekmesi 4 alt sekmeye bölündü (yine conditional router):

```python
_HG_SUBSECTIONS = ["Etkinlikler", "Afiş Modu", "Liste Modu", "Önizleme"]
```

Ana fonksiyonlar:
- `_admin_halkgunu()` — orchestrator, ortak etkinlik selectbox (alt sekmeler arası paylaşılır)
- `_admin_halkgunu_events()` — etkinlik CRUD (Hafta UI'ı paterni)
- `_admin_halkgunu_poster_mode()` — Afiş Modu (sayfa yönetimi + phase toggle)
- `_admin_halkgunu_mapping_phase()` — bbox eşleştirme (Ara'nın `_mapping_tool_tab`'ı baz alındı)
- `_admin_halkgunu_list_mode()` — Excel + ürün resmi yükleme

Yardımcı fonksiyonlar:
- `_hgmt_session_keys(event_id)` — etkinlik scoped session state key map
- `_hgmt_save_local()`, `_hgmt_flush_to_supabase()` — pending-then-flush model
- `_hg_image_to_jpeg()` — PNG/JPEG'i JPEG'e normalize
- `_hg_resolve_excel_columns()` — fuzzy Türkçe kolon eşleme

### Önemli pattern'ler (DEĞİŞTİRMEYİN)

1. **Conditional router** — `st.tabs()` her sekmeyi her rerun'da çalıştırır. Bu kullanılmıyor.
2. **Pre-indexed search** — `mapping_ui.search.build_search_index` Halk Günü mapping'inde de kullanılır
3. **Bulk DB operations** — `_mt_flush_to_supabase` benzeri toplu insert/delete/update
4. **Stable identity** — radio/selectbox'lar pozisyonel index yerine `urun_kod` / `mapping_id` kullanır
5. **Pending-then-flush** — kullanıcı kaydete basana kadar değişiklikler in-memory; flush'ta bulk
6. **Per-event session state** — `hgmt_*_{event_id}` ile etkinlikler arası karışmıyor

---

## Kod Rehberi — halkgunu Tarafı

### `src/app/page.tsx` (Orchestrator)
Akış:
1. `listActiveEvents()` → `EventTabs` → kullanıcı bir etkinlik seçer
2. Aktif etkinlik için `listEventPages()` çağrılır → `hasPoster` belirlenir
3. `hasPoster && hasList` ise `ModeToggle` görünür (yoksa default Liste)
4. Mode'a göre `ListView` veya `PosterView` render edilir
5. Bir ürüne tıklanınca `StoreModal` açılır

### `src/lib/api.ts`
DB sorguları:
- `listActiveEvents` — `halkgunu_events.status='active'`
- `listEventPages` — `halkgunu_pages` (sort_order, filename, page_no asc)
- `listEventMappings` — `halkgunu_mappings`
- `listEventProductSummary` — `halkgunu_products` distinct + JS-side aggregation
  (admin'in `get_event_product_summary` Python fonksiyonunun TS karşılığı; RPC
  yapmadık çünkü PostgREST üzerinden çekip JS'de gruplamak yeterli)
- `getProductStores` — RPC `get_halkgunu_product_stores`

### Tasarım kararları (frontend)

- **Renkler**: Ara'nın admin header gradient'ı (`#667eea → #764ba2`)
- **Mağaza kartı**: Ara'nın stok kartı stiliyle birebir aynı (linear gradient,
  sol border, yol tarifi rozeti)
- **Resim caching**: Image component yerine `<img>` kullandık (basit, lazy
  loading, error fallback). Next.js Image optimization Supabase storage için
  ekstra config gerektirir, kaçındık
- **PWA YOK**: halkgunu.net direkt servis edilir; iyibulur.com PWA wrapper'ı
  yalnızca Ara için
- **TR locale**: `Intl.NumberFormat("tr-TR")` ve `Intl.DateTimeFormat("tr-TR")`
  kullanıldı; `String.localeCompare("tr")` ile Türkçe sıralama

---

## Yapılan Fazlar

| Faz | İçerik | Commit SHA (Ara) |
|---|---|---|
| 1 | SQL şema (`halkgunu_schema.sql`) | `87835ca` |
| 2 | `halkgunu_storage.py` + admin Etkinlikler sekmesi | `7d293fd` |
| 3 | Liste Modu (Excel + ürün resmi tek/toplu) | `9e7d0bd` |
| 4a | Afiş Modu — sayfa yönetimi (PDF/JPG yükleme) | `1a9af1a` |
| 4b | Bbox eşleştirme (mapping editor) | `ac83800` |
| 6 | halkgunu-web Next.js (sonra ayrı repo'ya taşındı) | `68bde6e` |
| 6+ | halkgunu-web Ara'dan kaldırıldı | `8a0b723` |

> Faz 5 (Önizleme) atlandı — gerçek frontend (Faz 6) zaten önizleme görevi görüyor.

Tüm fazlar Ara'da `claude/halkgunu` branch'inde, `origin/claude/halkgunu`'ya
push edildi. `main`'e merge için PR açılması gerek.

---

## Mevcut Durum

### Ara repo'sunda
- Branch: `claude/halkgunu` (push edildi, **main'e merge edilmedi**)
- `halkgunu_schema.sql` — Supabase'de çalıştırılması gerek
- `halkgunu_storage.py` — hazır
- `urun_ara_app.py` — admin sekmesi hazır
- `halkgunu-web/` klasörü kaldırıldı (8a0b723 ile)
- Geçici branch `halkgunu-web-standalone` push edildi → silinmesi gerek
  (`git push origin --delete halkgunu-web-standalone`)

### halkgunu repo'sunda
- Branch: `main` (tek commit: `b95da01`)
- Vercel'e bağlandı, ilk build **fail oldu** (eksik dosyalar — bkz aşağı)
- Domain `halkgunu.net` henüz bağlanmadı

### Supabase'de
- `halkgunu_schema.sql` çalıştırılmadı → kullanıcının yapması gerek
- Bucket'lar mevcut (`poster-images`, `product-images`) — Ara zaten kullanıyor

### Vercel'de
- `senirlioglu/halkgunu` projesi kuruldu
- Env vars eklenmesi gerekebilir: `NEXT_PUBLIC_SUPABASE_URL`,
  `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- Domain bağlama bekleniyor

---

## Bilinen Sorunlar

### 🔴 1. halkgunu repo'sunda `src/lib/` eksik

**Sebep**: Ara'nın `.gitignore` dosyasının 13. satırında `lib/` var (Python
build artifact için). Bu pattern halkgunu-web Next.js projesinin
`src/lib/` klasörünü de yakaladı, dolayısıyla ilk commit (`68bde6e`)
sırasında `git add` 4 dosyayı sessizce hariç tuttu:

```
halkgunu-web/src/lib/api.ts
halkgunu-web/src/lib/format.ts
halkgunu-web/src/lib/supabase.ts
halkgunu-web/src/lib/types.ts
```

Subtree split sonra bu eksiği kopyaladı, halkgunu repo'sunda da yok.
Vercel build hatası: `Module not found: Can't resolve '@/lib/api'`

**Çözüm seçenekleri**:
- **A (önerilen)**: Lokal halkgunu klonunda 4 dosyayı manuel oluştur
  (içerikleri bu doküman'da değil — Ara'nın `claude/halkgunu` branch
  geçmişinde yok; bir sonraki Claude session'ında yeniden üret veya bu
  oturumun konuşma geçmişinden kopyala)
- **B**: Ara'nın `.gitignore`'ında `lib/` → `/lib/` (sadece root) yapıp
  halkgunu-web'i Ara'da yeniden oluştur, subtree split, force push
  halkgunu/main'e

**4 dosyanın özeti**:
- `supabase.ts` — `createClient` + `productImageUrl(kod)` + `posterImageUrl(path)`
- `types.ts` — `HalkgunuEvent`, `HalkgunuPage`, `HalkgunuMapping`,
  `HalkgunuProductSummary`, `HalkgunuProductStore`, `EventStatus`
- `api.ts` — `listActiveEvents`, `listEventPages`, `listEventMappings`,
  `listEventProductSummary` (JS-side aggregation), `getProductStores` (RPC)
- `format.ts` — `formatPrice` (TRY), `formatEventDate`, `formatShortDate`,
  `discountPercent`

### 🟡 2. Ara'nın `.gitignore`'ında `lib/` kuralı

`lib/` (root + her alt klasör) Python build artifact için ama Next.js'te
yanıltıcı. **Önerilen düzeltme**: `lib/` → `/lib/` yap ki sadece root'ta
ignore etsin. Halk Günü sorunundan sonra yapılması gereken küçük bir tidy.

### 🟡 3. Ara `claude/halkgunu` branch'i `main`'e merge edilmedi

CLAUDE.md kuralı: "main'e direkt push yapmayın — PR ile merge edin".
PR açılması ve review sonrası merge gerek. Streamlit Cloud `main` branch'ini
otomatik deploy ettiği için merge edilince Halk Günü canlıya çıkar.

### 🟡 4. Geçici branch temizliği

Ara remote'unda `halkgunu-web-standalone` branch'i hâlâ var (kullanıcının
silmesi gerek; sandbox'tan silmek için yetkim yetmedi).

---

## Tasarım Kararları (KRİTİK)

Bu kararları değiştirmeden önce iki kez düşünün:

1. **Aynı Supabase, ayrı repo**: halkgunu Ara'nın altyapısını yeniden
   keşfetmiyor; magazalar, stok_gunluk, product-images bucket aynen okunuyor.
2. **`magaza_ad` denormalize edilmedi**: halkgunu_products yalnızca
   `magaza_kod` taşır. `magazalar` join'i ile zenginleştirilir. Bu, Ara'da
   mağaza adı değişirse halkgunu'da otomatik yansır.
3. **Tek Excel kaynağı**: Halk Günü'nde Excel YALNIZCA Liste Modu'nda yüklenir.
   Afiş Modu mapping queue'sunu aynı `halkgunu_products`'tan distinct
   `urun_kod` ile çeker. Tek source-of-truth.
4. **Storage path namespacing**: Hem Ara hem halkgunu `poster-images`
   bucket'ını paylaşır. `halkgunu/{event_id}/...` prefix'i çakışma engeller.
5. **Per-event session state**: Admin'de etkinlikler arası geçerken state
   karışmaması için `hgmt_*_{event_id}` pattern'i.
6. **Pending-then-flush**: Bbox eşleştirmede her tıklama Supabase'e gitmiyor;
   in-memory toplanıp tek seferde bulk yazılıyor (Ara pattern'i).
7. **JS-side aggregation**: Frontend `halkgunu_products`'tan distinct ürün
   listesi için ayrı RPC değil, PostgREST + JS reduce kullanır. Daha az iş.
8. **Frontend `<img>` taglar**: Next.js `<Image>` yerine düz `<img>` kullandık
   (Supabase storage için ekstra remote pattern config gerekir, kaçındık;
   lazy loading + onError fallback yeterli).

---

## Sıradaki Adımlar

### Önce yapılacaklar (Halk Günü canlıya çıksın diye):

1. **halkgunu repo'sunda eksik 4 dosya** — `src/lib/api.ts`, `format.ts`,
   `supabase.ts`, `types.ts` oluştur, commit + push
   - Vercel otomatik redeploy yapar, build başarılı olmalı
2. **Supabase'de `halkgunu_schema.sql` çalıştır**
3. **Vercel env vars** — `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
4. **Domain `halkgunu.net`** — Vercel project → Domains
5. **Ara `claude/halkgunu` → `main` PR** — CLAUDE.md kuralı

### Sonra (sıralı değil, yapılırsa hoş):

1. Ara `.gitignore` `lib/` → `/lib/` (önemsiz tidy)
2. Ara'da `halkgunu-web-standalone` geçici branch'i sil
3. Frontend için Supabase RLS politikalarını gözden geçir (anon key okumaları)
4. SEO için `src/app/sitemap.ts` ve `robots.txt`
5. Önizleme sekmesi (Faz 5) — admin'de iframe ile localhost:3000 göster
6. Halk Günü Excel template'i README'ye ekle (kullanıcı için kolay başlangıç)
7. Frontend testleri (Playwright) — etkinlik akışı, modal, vb
8. Ara'nın TypeScript geçişi (CLAUDE.md madde 2) — halkgunu yapısı bunun için
   referans olur

---

## Çalıştırma / Test

### Ara (Streamlit) — local
```bash
pip install -r requirements.txt
streamlit run urun_ara_app.py
# Admin için: ?admin=true + ADMIN_PASSWORD env var
```

### halkgunu (Next.js) — local
```bash
cp .env.local.example .env.local  # Supabase URL/KEY ekle
npm install
npm run dev
# http://localhost:3000
```

### End-to-end test akışı
1. Supabase'de SQL şemayı yükle
2. Ara'da admin → Halk Günü → Etkinlikler → "+ Yeni Etkinlik" oluştur
3. Liste Modu → Excel yükle (kolonlar: ürün kodu, ürün adı, mağaza kodu,
   normal fiyat, indirimli fiyat — TR/EN ad esnektir)
4. Afiş Modu → Sayfa Yönetimi → PDF/JPG yükle
5. Afiş Modu → Bbox Eşleştirme → kutu çiz + ürün seç + kaydet
6. Liste Modu → Toplu Resim Yükle (eksik resimler için)
7. Etkinlikler → "Yayınla" (status `active`)
8. halkgunu.net (veya `npm run dev`) → tarih sekmesi → ürün → mağaza listesi

### Excel kolon esnekliği
Otomatik eşleştirilen alias'lar (büyük/küçük + Türkçe karakter farketmez):
- `urun_kod`: urun_kod, urun_kodu, kod, sku, stok_kodu
- `urun_ad`: urun_ad, urun_adi, urun_aciklamasi, aciklama
- `magaza_kod`: magaza_kod, magaza_kodu, sube_kod
- `normal_fiyat`: normal_fiyat, liste_fiyati, etiket_fiyat
- `indirimli_fiyat`: indirimli_fiyat, kampanya_fiyati, halkgunu_fiyat

---

## Ara Projesi Altyapısı (referans)

> Bu kısım `CLAUDE.md` özeti — yeni session'ın hızlı bağlam için.

- **Stack**: Streamlit + Supabase + Streamlit Cloud (main → otomatik deploy)
- **Kullanıcı tarafı**: iyibulur.com (PWA wrapper) → iframe → Ara
- **Admin**: `ara101.streamlit.app/?admin=true`, conditional router (st.tabs YOK)
- **Tablolar**: `stok_gunluk`, `magazalar`, `poster_weeks`, `poster_pages`,
  `mappings`, `week_products`, `arama_log` + Halk Günü için 4 yeni tablo
- **Bucket'lar**: `poster-images`, `product-images`
- **Custom components**: `components/bbox_canvas/`, `components/poster_viewer/`
  — Halk Günü mapping editor `bbox_canvas`'ı yeniden kullanır (fork yok)
- **Ürün master pipeline**: `urun_master_pipeline.py` GitHub Actions ile
  her gün 10:30 TR'de çalışır
- **Önemli performans kararları**: pre-indexed search, conditional router,
  bulk DB ops, stable identity, per-event/week scoped session state

---

## Bağlantılar

- Ara repo: https://github.com/senirlioglu/Ara
- halkgunu repo: https://github.com/senirlioglu/halkgunu
- Streamlit deploy: https://ara101.streamlit.app
- (yakında) halkgunu deploy: https://halkgunu.net

---

## Geçmiş Komutlar (referans)

```bash
# Subtree split (halkgunu-web → standalone)
git subtree split --prefix=halkgunu-web -b halkgunu-web-standalone

# Yeni repo'ya yansıtma (kullanıcı yapacak)
git remote add halkgunu git@github.com:senirlioglu/halkgunu.git
git push halkgunu halkgunu-web-standalone:main

# Geçici branch silme
git branch -D halkgunu-web-standalone           # local
git push origin --delete halkgunu-web-standalone # remote
```

---

*Bu doküman `claude/halkgunu` branch'inde Ara repo'sunda saklanır.
Yeni bir Claude Code session'ı bunu okuyup Halk Günü ile ilgili tüm
bağlamı tek seferde alabilir.*
