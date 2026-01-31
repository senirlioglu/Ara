# Launcher - iOS Home Screen Icon Fix

Bu klasor, iOS "Ana Ekrana Ekle" ikonunu duzeltmek icin wrapper sayfasi icerir.

## Neden Gerekli?

Streamlit Cloud'da:
- Root'a (`/apple-touch-icon.png`) statik dosya servis edilemiyor
- JavaScript ile head manipulasyonu calismiyor
- iOS her zaman Streamlit logosunu kullaniyor

## Kurulum

1. Bu klasordeki dosyalari **GitHub Pages**, **Vercel**, veya **Cloudflare Pages**'e deploy edin

2. `index.html` dosyasinda `YOUR_STREAMLIT_URL` yerine gercek Streamlit Cloud URL'nizi yazin:
   ```html
   <iframe src="https://your-app-name.streamlit.app/?embed=true" ...>
   ```

3. Kullanicilara bu yeni URL'yi verin (orn: `https://yourusername.github.io/urun-ara-launcher/`)

## Kullanici Talimatlari

1. Safari'de launcher URL'yi acin
2. Share butonu -> "Ana Ekrana Ekle"
3. Artik ana ekrandaki ikon sizin ozel ikonunuz olacak

## Dosyalar

- `index.html` - Ana wrapper sayfa (Streamlit'i iframe icinde acar)
- `manifest.json` - PWA manifest (Android icin)
- `apple-touch-icon.png` - iOS ikon (180x180)
- `icon-192.png` - PWA ikon (192x192)
- `icon-512.png` - PWA ikon (512x512)
- `favicon.png` - Tarayici favicon

## GitHub Pages ile Hizli Kurulum

1. Yeni repo olusturun: `urun-ara-launcher`
2. Bu klasordeki tum dosyalari repo'ya yukleyin
3. Settings -> Pages -> Source: "Deploy from a branch" -> Branch: `main` -> `/ (root)`
4. URL'niz: `https://USERNAME.github.io/urun-ara-launcher/`
