# Code Review - Ürün Arama Uygulaması (Ara)

**Tarih:** 2026-02-26
**Reviewer:** Claude Code Review
**Proje:** Streamlit tabanlı ürün arama uygulaması (Supabase/PostgreSQL backend)

---

## Genel Değerlendirme

Proje, perakende mağazalarda stok sorgulaması yapan bir Streamlit web uygulamasıdır. Supabase üzerinden PostgreSQL'e bağlanarak server-side arama yapar, autocomplete desteği sunar ve admin analitik paneli içerir. PWA desteği ile mobil kullanıma uygun hale getirilmiştir.

**Genel Puan: 7/10** - Çalışan, kullanışlı bir uygulama. Ancak güvenlik, kod organizasyonu ve bakım kolaylığı açısından iyileştirme alanları mevcut.

---

## 1. Güvenlik Sorunları

### 1.1 KRITIK: Admin Paneli MD5 Token Zayıflığı
**Dosya:** `urun_ara_app.py:924`
```python
valid_token = hashlib.md5(f"{admin_pass}{today}".encode()).hexdigest()[:16]
```
- MD5 kriptografik olarak zayıf bir hash algoritmasıdır. `hashlib.sha256` veya `secrets.token_hex` kullanılmalıdır.
- Token sadece 16 karakter (8 byte) olarak kesiliyor, bu brute-force olasılığını artırır.
- Token URL'de `?token=...` olarak taşınıyor, bu da tarayıcı geçmişi ve log dosyalarına sızma riski taşır.

**Öneri:**
```python
import hmac, hashlib
valid_token = hmac.new(admin_pass.encode(), today.encode(), hashlib.sha256).hexdigest()[:32]
```

### 1.2 ORTA: Bare `except` Kullanımı (Yaygın)
**Dosyalar:** `urun_ara_app.py:35, 142, 429, 439, 510, 536`, `urun_master_pipeline.py` çeşitli yerler
```python
except:
    pass
```
- Bare `except` tüm hataları (KeyboardInterrupt, SystemExit dahil) yutarak hata ayıklamayı imkansız hale getirir.
- En azından `except Exception` kullanılmalı ve loglama eklenmelidir.

### 1.3 DÜŞÜK: HTML Injection Riski
**Dosya:** `urun_ara_app.py:694-720`
- `magaza_ad`, `sm`, `bs` gibi veritabanından gelen değerler doğrudan HTML'e yerleştiriliyor (`unsafe_allow_html=True`).
- Veritabanındaki kötü niyetli veri ile XSS saldırısı mümkün.
- `html.escape()` ile sanitize edilmeli.

---

## 2. Mimari ve Tasarım

### 2.1 Tek Dosyada Çok Fazla Sorumluluk
**Dosya:** `urun_ara_app.py` (1080 satır)
- UI, iş mantığı, veritabanı erişimi, CSS, JavaScript, admin paneli hepsi tek dosyada.
- Önerilen yapı:
  ```
  app/
  ├── main.py           # Entry point
  ├── search.py         # Arama mantığı
  ├── admin.py          # Admin paneli
  ├── db.py             # Supabase client
  ├── normalize.py      # Metin normalizasyonu
  ├── styles.py         # CSS stilleri
  └── components.py     # UI bileşenleri
  ```

### 2.2 Normalize Fonksiyonu Duplikasyonu
- `temizle_ve_kok_bul()` (`urun_ara_app.py:162-226`) ve `normalize_urun_ad()` (`urun_master_pipeline.py:27-61`) neredeyse aynı mantığı tekrar ediyor.
- Tek bir paylaşılan modüle taşınmalı. Biri değişip diğeri değişmezse arama tutarsızlıkları yaşanır.

### 2.3 Client-Side JavaScript (Autocomplete)
**Dosya:** `urun_ara_app.py:761-877`
- ~120 satırlık minified JavaScript string literal olarak Python dosyasının içinde.
- Bu JS kodu test edilemiyor ve bakımı zor. Ayrı bir `.js` dosyasına taşınmalı.
- `__DATA__` placeholder'ı ile string replace yapılması, büyük veri setlerinde bellek sorunu yaratabilir (725KB'lık JSON inline gönderiliyor).

---

## 3. Performans

### 3.1 Büyük JSON Verisi Client'a Gönderiliyor
**Dosya:** `urun_ara_app.py:760`
- `oneri_listesi.json` (725KB) her sayfa yüklemesinde client-side'a gönderiliyor.
- Mobil kullanıcılar için ağır. Sunucu tarafında filtreli API endpoint veya lazy-loading tercih edilmeli.

### 3.2 Fallback Arama Zinciri - Potansiyel Yavaşlık
**Dosya:** `urun_ara_app.py:413-469`
- Birincil arama başarısız olursa 5 aşamalı fallback zinciri çalışıyor.
- Her aşamada ayrı RPC çağrısı yapılıyor. En kötü durumda 6 veritabanı çağrısı yapılabilir.
- Bu, yavaş ağ bağlantılarında kullanıcı deneyimini ciddi şekilde olumsuz etkiler.

**Öneri:** Fallback mantığını SQL fonksiyonuna taşıyarak tek bir RPC çağrısında çözmek.

### 3.3 `df.apply()` Kullanımı
**Dosya:** `urun_ara_app.py:369`
```python
df['alaka'] = df.apply(calculate_relevance, axis=1)
```
- `apply(axis=1)` satır bazlı Python loop'u çalıştırır, vectorized operasyonlara göre çok yavaştır.
- Büyük sonuç setlerinde (binlerce satır) darboğaz oluşturur.

---

## 4. Hata Yönetimi

### 4.1 Sessiz Hata Yutma
Birçok yerde hatalar sessizce yutulmuş:
```python
# urun_ara_app.py:429
except: pass

# urun_ara_app.py:510
except:
    pass
```
- Bu durumlarda en azından `logging.exception()` ile loglama yapılmalı.

### 4.2 Supabase Client None Kontrolü
**Dosya:** `urun_ara_app.py:133-143`
```python
def get_supabase_client():
    try:
        ...
        if not url or not key:
            return None
        return create_client(url, key)
    except:
        return None
```
- Client `None` döndüğünde uygulama sessizce çöküyor. Kullanıcıya daha açıklayıcı hata mesajları verilmeli.
- `@st.cache_resource` ile cache'lenmiş `None` değeri sorunlu - bir kez `None` dönerse restart edene kadar düzelmez.

---

## 5. Kod Kalitesi

### 5.1 Kullanılmayan/Tutarsız İmportlar
**Dosya:** `urun_ara_app.py:758`
```python
import json  # Zaten satır 18'de import edilmiş
```

### 5.2 Magic Number'lar
**Dosya:** `urun_ara_app.py` çeşitli yerler
- `len(optimize_sorgu) >= 7` (satır 330) - neden 7?
- `top_n = 40` (satır 618) - neden 40?
- `[:100]` (satır 485) - terim uzunluk limiti neden 100?
- Bu değerler sabit (constant) olarak tanımlanmalı.

### 5.3 Yazım Düzeltme Sözlüğünde Duplikasyon
**Dosya:** `urun_ara_app.py:250-258`
```python
'wafle': 'waffle', 'vafle': 'waffle', 'wafle': 'waffle',  # 'wafle' iki kez
'kulaklik': 'kulaklik',  # Kendisiyle eşleşiyor (no-op)
'supurge': 'supurge',    # Kendisiyle eşleşiyor (no-op)
'camasir': 'camasir',    # Kendisiyle eşleşiyor (no-op)
'bulasik': 'bulasik',    # Kendisiyle eşleşiyor (no-op)
'sampuan': 'sampuan',    # Kendisiyle eşleşiyor (no-op)
```
- Duplike anahtar ve no-op eşleşmeler temizlenmeli.

### 5.4 `cold` → `gold` Düzeltmesi Riskli
**Dosya:** `urun_ara_app.py:240`
```python
'cold': 'gold',
```
- Genel bir kelime olan `cold` her zaman `gold` olarak düzeltilecek. Bu bağlam dışı yanlış sonuçlara neden olabilir ("cold brew" → "gold brew").

---

## 6. Veritabanı ve SQL

### 6.1 SQL Dosyası ile Uygulama Uyumsuzluğu
- `supabase_turkish_search.sql` dosyasında `products` tablosu tanımlı, ancak uygulama `stok_gunluk` tablosunu kullanıyor.
- `search_products` RPC fonksiyonu SQL dosyasında var, ancak uygulama `hizli_urun_ara` fonksiyonunu çağırıyor.
- SQL dosyası güncel prodüksiyon durumunu yansıtmıyor. Dokümantasyon olarak yanıltıcı.

### 6.2 TypeScript Client Kullanılmıyor
- `supabase_search_client.ts` dosyası mevcut ama uygulamada kullanılmıyor.
- Eğer gelecekte kullanılacaksa ayrı bir `docs/` veya `examples/` klasörüne taşınmalı, değilse kaldırılmalı.

---

## 7. CI/CD ve DevOps

### 7.1 GitHub Actions Workflow
**Dosya:** `.github/workflows/build-urun-master.yml:9`
```yaml
push:
  branches:
    - 'iokvoq-codex/fix-autocomplete-and-search-suggestions'
```
- Belirli bir feature branch'e push tetikleyicisi var. Bu muhtemelen geçici ve temizlenmeli.
- `master` veya `main` branch'e taşınmalı.

### 7.2 Test Eksikliği
- Projede hiç test dosyası yok (`*_test.py`, `test_*.py`, `tests/`).
- En azından normalize fonksiyonları, yazım düzeltme sözlüğü ve arama query routing mantığı test edilmeli.

---

## 8. PWA ve Frontend

### 8.1 index.html Hardcoded URL
**Dosya:** `index.html:128`
```html
src="https://Ara101.streamlit.app/?embed=true"
```
- Streamlit app URL'si hardcoded. Environment-specific yapılandırma ile değiştirilmeli.

### 8.2 Google Analytics
**Dosya:** `index.html:7-13`
- GA tracking ID hardcoded. Eğer farklı ortamlar (dev/staging/prod) varsa, bu sorun olabilir.

---

## 9. Yapılması Gerekenler (Öncelik Sırası)

| Öncelik | Konu | Dosya | Efor |
|---------|------|-------|------|
| P0 | MD5 token → SHA256 | `urun_ara_app.py` | Düşük |
| P0 | HTML escape ekle (XSS) | `urun_ara_app.py` | Düşük |
| P1 | Bare `except` → `except Exception` + log | Tüm dosyalar | Düşük |
| P1 | Normalize fonksiyonu birleştir | `urun_ara_app.py`, `urun_master_pipeline.py` | Orta |
| P1 | Yazım sözlüğü duplikasyonlarını temizle | `urun_ara_app.py` | Düşük |
| P2 | Autocomplete JS'i ayrı dosyaya taşı | `urun_ara_app.py` | Orta |
| P2 | Test eklenmesi | Yeni dosya | Yüksek |
| P2 | Fallback aramayı SQL'e taşı | `supabase_turkish_search.sql` | Yüksek |
| P3 | Tek dosyayı modüllere ayır | `urun_ara_app.py` | Yüksek |
| P3 | Kullanılmayan dosyaları temizle/organize et | `supabase_search_client.ts` vb. | Düşük |

---

## 10. Olumlu Yönler

- **Türkçe arama normalizasyonu** iyi düşünülmüş. SQL ve Python tarafı uyumlu çalışıyor.
- **Query Router** (kod vs metin araması ayrımı) akıllı bir yaklaşım.
- **Fallback arama zinciri** kullanıcının bir şekilde sonuç bulmasını sağlıyor.
- **PWA desteği** (manifest.json, service worker, apple-touch-icon) mobil kullanım için iyi.
- **Admin analitik paneli** arama trendlerini izlemeye olanak tanıyor.
- **Stok seviyesi badge sistemi** (Yok/Düşük/Orta/Yüksek) kullanıcı dostu bir UX sunuyor.
- **Google Maps entegrasyonu** ile mağaza yol tarifi özelliği pratik.
- **CI/CD pipeline** ile ürün master verisinin otomatik güncellenmesi iyi yapılandırılmış.
- **Yazım düzeltme sözlüğü** gerçek kullanıcı hatalarından derlenmiş, bu pratik bir yaklaşım.

---

*Bu review, kodun mevcut durumunu değerlendirir. Öneriler, projenin kapsamı ve kaynakları göz önünde bulundurularak önceliklendirilmelidir.*
