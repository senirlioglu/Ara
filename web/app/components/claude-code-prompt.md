# StokBul - Tasarım Promptu (Mor-Turuncu Gradient Versiyon)

## Proje Açıklaması
StokBul, kullanıcıların ürün adı/kodu/barkod ile arama yaparak hangi mağazada hangi ürünün bulunduğunu, fiyat ve stok bilgisini görebildiği tek sayfalık mobil-öncelikli web uygulamasıdır.

## Teknoloji Stack
- React 18 + TypeScript + Vite
- Tailwind CSS v3 + tailwindcss-animate
- Lucide React (ikonlar)
- Google Fonts: Plus Jakarta Sans (tüm metinler, 400-800 ağırlık)

## Tasarım Dili
- **Hero Gradient:** Mor → Mavi → Turuncu (135deg, hsl(260 60% 55%) → hsl(220 60% 50%) → hsl(25 95% 53%))
- **Primary:** Turuncu (25 95% 53%) - arama butonu, aktif elemanlar
- **Accent:** Mor (260 60% 55%)
- **Arka plan:** Sıcak bej-gri (30 20% 98%)
- **Kartlar:** Beyaz, ince border, yumuşak gölge
- **Stok renkleri:** Yeşil (Yüksek), Sarı (Orta), Kırmızı (Düşük)
- **Fiyat badge:** Kırmızı arka plan (bg-red-500)
- **Bölge stok badge:** Yeşil arka plan (bg-green-500)
- **Border radius:** 0.75rem
- **Font:** Plus Jakarta Sans, kalın başlıklar (font-extrabold, font-bold)

## Sayfa Yapısı (Tek Sayfa - SPA)
1. **Hero Header:** Mor-turuncu gradient, "Ürün Ara" başlığı (beyaz, extrabold), pt-8 pb-12
2. **Arama Çubuğu:** Hero'nun altına taşan (-mt-6), beyaz kart, Search ikonu + input + ScanBarcode butonu + "Ara" butonu (turuncu/20 opacity arka plan, turuncu yazı)
3. **Popüler Aramalar:** Yatay kaydırılabilir (overflow-x-auto, scrollbar gizli), "Popüler Aramalar" başlığı (sm, bold), beyaz etiketler
4. **Sonuç Sayısı:** "X ürün bulundu · 📍 Yakınına göre sıralı" (X turuncu bold, sıralama kırmızı)
5. **Ürün Kartları:** Genişletilebilir (expandable), tıkla-aç/kapa (ChevronDown/Up)
6. **Haftalık Broşür:** Tab'lı (aktif tab kırmızı), broşür görseli

## Ürün Kartı Detayları
- Ürün adı (bold, base size)
- Fiyat badge (bg-red-500, beyaz yazı, rounded-lg)
- Ürün kodu + mağaza sayısı (bold) + "Bölge Stok: X" badge (yeşil)
- Tıklanınca açılan mağaza listesi:
  - Sıralama: Yakınlık (MapPin ikonu, bg-muted) / Stok (📦, bg-primary)
  - Her mağaza: isim (bold) + mesafe (km, gri badge) + "Yol tarifi" (kırmızı, MapPin) + stok badge
  - SM/BS personel bilgisi + kod

## Dosya Yapısı
Bu dosyaları projeye uygula:
- `index.css` → `src/index.css`
- `tailwind.config.ts` → `tailwind.config.ts`
- `index.html` → `index.html`
- `HeroHeader.tsx` → `src/components/HeroHeader.tsx`
- `SearchBar.tsx` → `src/components/SearchBar.tsx`
- `PopularSearches.tsx` → `src/components/PopularSearches.tsx`
- `ProductCard.tsx` → `src/components/ProductCard.tsx`
- `WeeklyBrochures.tsx` → `src/components/WeeklyBrochures.tsx`
- `Index.tsx` → `src/pages/Index.tsx`

## Önemli Notlar
- Mobil öncelikli (440px viewport)
- Tüm renkler HSL CSS custom properties
- Dark mode desteği (.dark class) hazır
- Popüler aramalar yatay scroll, dikey değil
- Arama yapılmasa bile mock ürünler görünsün
- Mağaza kartları her zaman gösterilsin (expanded state)
