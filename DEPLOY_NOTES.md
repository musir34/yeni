# 🚀 Sunucuya Deploy Notları

## Tarih: 2025-12-25

### ✅ Yapılan Değişiklikler

#### 1. **Idefix API Kimlik Doğrulama Düzeltmesi**
- **Dosya**: `idefix/idefix_service.py`
- **Sorun**: `X-API-KEY` header'ı yerine `Authorization: Basic` kullanılması gerekiyordu
- **Çözüm**: Header formatı düzeltildi
```python
# ÖNCEDEN:
"X-API-KEY": self._get_vendor_token()

# ŞİMDİ:
"Authorization": f"Basic {self._get_vendor_token()}"
```

#### 2. **Trendyol Sipariş Güncelleme Kontrolü**
- **Dosya**: `update_service.py`
- **İyileştirmeler**:
  - Stok düşmezse Trendyol'a güncelleme gönderilmez
  - Trendyol güncellemesi başarısızsa stok düşümü geri alınır
  - Detaylı hata logları eklendi
  - API response body'deki hata mesajları kontrol edilir

#### 3. **404 Hata Loglarını Filtreleme**
- **Dosya**: `app.py`
- **Değişiklik**: `/static/` dosyaları için 404 hatası loglanmaz (spam önleme)

#### 4. **Default Görsel Oluşturma**
- **Dosya**: `static/images/default.jpg` oluşturuldu

---

## 📦 Sunucuya Deploy Adımları

### 1. Dosyaları Sunucuya Yükle
```bash
# Lokal makinede
scp update_service.py musir@138.199.218.72:~/gullupanel/yeni/
scp idefix/idefix_service.py musir@138.199.218.72:~/gullupanel/yeni/idefix/
scp app.py musir@138.199.218.72:~/gullupanel/yeni/
scp static/images/default.jpg musir@138.199.218.72:~/gullupanel/yeni/static/images/
```

### 2. Sunucuda Uygulamayı Yeniden Başlat
```bash
# Sunucuda
cd ~/gullupanel/yeni

# Gunicorn'u durdur
if [ -f gullupanel.pid ]; then kill $(cat gullupanel.pid) || true; fi

# 2 saniye bekle
sleep 2

# Yeniden başlat
nohup ../venv/bin/gunicorn -w 4 app:app -b 127.0.0.1:8000 --pid gullupanel.pid &

# Logları kontrol et
tail -f nohup.out
```

---

## 🔍 Beklenen Sonuçlar

### Idefix API
- ✅ 401 hataları düzelmeli
- ✅ Stok güncellemeleri başarılı olmalı
- ✅ Logda `[IDEFIX] ✅ Batch X başarılı` görülmeli

### Trendyol Güncellemeleri
- ✅ Stok yetersizse güncelleme GÖNDERİLMEZ
- ✅ Logda: `[STOCK][CRITICAL] Hiç stok düşmedi! Trendyol'a güncelleme gönderilmiyor.`
- ✅ API hatası varsa: `[TYL][FAIL] sp_id=XXX` ve stok geri alınır

### Loglar
- ✅ Static dosya 404'leri artık yazılmaz
- ✅ Daha temiz log çıktısı

---

## 🐛 Sorun Giderme

### Idefix Hala 401 Dönüyorsa
1. Credentials'ları kontrol et:
```bash
cat .env | grep IDEFIX
```

2. Token'ın doğru encode edildiğini test et:
```python
import base64
token = "ca79481e-a7c5-4bd2-ad83-128e93b0c4fa"
secret = "9114521f-b876-438a-ae1b-bb676fa895d2"
vendor_token = base64.b64encode(f"{token}:{secret}".encode()).decode()
print(f"Authorization: Basic {vendor_token}")
```

3. Idefix API dokümantasyonunu kontrol et - belki header formatı farklı

### Trendyol Güncellemeleri Çalışmıyorsa
- Logları incele: `grep "TYL\|STOCK" nohup.out | tail -100`
- Stok düşümü kontrollerini gözlemle
- API yanıtlarını kontrol et

---

## 📝 Notlar

- Sunucuda Python 3.11 kullanılıyor
- Gunicorn 4 worker ile çalışıyor
- Scheduler aktif (DISABLE_JOBS=0)
- Her 4 dakikada bir otomatik stok push/pull

---

## ⚠️ DİKKAT

Eğer Idefix API dokümantasyonu farklı bir header formatı gerektiriyorsa (örneğin `Bearer` token), `idefix_service.py` dosyasındaki `_get_headers()` metodunu güncellemeniz gerekebilir.

Alternatif header formatları:
```python
# Opsiyon 1: Bearer token
"Authorization": f"Bearer {self.token}"

# Opsiyon 2: Basic auth (şu anki)
"Authorization": f"Basic {self._get_vendor_token()}"

# Opsiyon 3: Custom header
"X-VENDOR-TOKEN": self._get_vendor_token()
```
