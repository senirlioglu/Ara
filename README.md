# halkgunu-web

[halkgunu.net](https://halkgunu.net) için kullanıcı tarafı — Next.js 14 (App Router) + TypeScript + Tailwind + Supabase JS.

Aynı Supabase projesi Ara ile paylaşılır. İçerik yönetimi ([ara101.streamlit.app/?admin=true](https://ara101.streamlit.app/?admin=true)) Halk Günü sekmesinden yapılır.

## Geliştirme

```bash
cp .env.local.example .env.local
# .env.local içine NEXT_PUBLIC_SUPABASE_URL ve NEXT_PUBLIC_SUPABASE_ANON_KEY ekle

npm install
npm run dev
# http://localhost:3000
```

## Vercel Deploy

1. Vercel'de yeni proje oluştur (bu repo'yu bağla)
2. **Root Directory**: `halkgunu-web`
3. Environment Variables:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
4. Domain: `halkgunu.net` (Vercel project settings → Domains)

## Mimari

| Katman | Konum |
|---|---|
| Sayfa | `src/app/page.tsx` (orchestrator: tarih sekmeleri + mod toggle + view + modal) |
| Liste view | `src/components/ListView.tsx` |
| Afiş view | `src/components/PosterView.tsx` (clickable bbox overlay) |
| Mağaza modalı | `src/components/StoreModal.tsx` (Ara'nın kart stili) |
| Supabase client | `src/lib/supabase.ts` |
| API çağrıları | `src/lib/api.ts` |
| Tipler | `src/lib/types.ts` |

## Veri Akışı

1. `halkgunu_events` (status=active) → tarih sekmeleri
2. Aktif etkinlik için:
   - **Liste**: `halkgunu_products` → distinct ürün özeti → kart grid
   - **Afiş**: `halkgunu_pages` + `halkgunu_mappings` → poster üstüne overlay bbox
3. Ürüne tıklama → `get_halkgunu_product_stores(event_id, urun_kod)` RPC →
   `magazalar` + `stok_gunluk` join → mağaza listesi modalı

## Tasarım Notları

- Renkler ve gradient'lar Ara'nın admin header'ı baz alındı (`#667eea → #764ba2`)
- Mağaza kartı stili Ara'nın stok kartı ile birebir aynı (linear gradient, sol border, yol tarifi rozeti)
- PWA wrapper YOK — bu Vercel/Next.js direkt halkgunu.net'te servis edilir; iyibulur.com PWA wrapper'ı sadece Ara için
- Ürün resimleri `product-images` bucket'ından Ara ile paylaşılır (urun_kod ortak anahtar)
