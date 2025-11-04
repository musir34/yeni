# 🔍 Barkod Alias Hızlı Test Rehberi

## ✅ Sisteminiz Hazır!

Zaten bir alias eşleştirmeniz var:
- **Alias Barkod:** `008932232669`
- **Ana Barkod:** `Güllüayakkabı048`
- **Ekleyen:** musir

## 🚀 Hızlı Kontrol Yöntemleri

### 1️⃣ Terminal Test (En Hızlı)

```bash
# Tüm alias'ları listele
python test_alias.py --list

# Belirli bir barkodu test et
python test_alias.py 008932232669

# Ana barkodu test et
python test_alias.py Güllüayakkabı048
```

### 2️⃣ Web Arayüzü
1. Anasayfa → **Ürün İşlemleri** → **🔖 Barkod Alias Yönetimi**
2. Sayfada tüm alias'ları görürsünüz

### 3️⃣ Raf Sisteminde Test
```bash
# Alias ile ürün ara
curl http://localhost:5000/raf/api/ara/008932232669

# Ana barkod ile ürün ara
curl http://localhost:5000/raf/api/ara/Güllüayakkabı048
```

### 4️⃣ API ile Test
```bash
# Normalize et
curl http://localhost:5000/barcode-alias/api/normalize/008932232669

# Barkod bilgisi
curl http://localhost:5000/barcode-alias/api/check/008932232669
```

## 📊 Test Sonuçları

### ✅ Alias Barkod (008932232669)
```
Normalize Edilmiş: Güllüayakkabı048
Alias mi?: EVET ✓
Ana Barkod: Güllüayakkabı048
```

### ✅ Ana Barkod (Güllüayakkabı048)
```
Normalize Edilmiş: Güllüayakkabı048
Alias mi?: HAYIR ✗
Bağlı Alias'lar: 1 adet
  • 008932232669
```

## 🎯 Gerçek Kullanımda Test

### Raf Sisteminde:
1. Raf sayfasına git: `/raf/yonetim`
2. Barkod ara kısmına `008932232669` yaz
3. Sistem `Güllüayakkabı048` olarak bulmalı ✓

### Sipariş Hazırlamada:
1. Sipariş hazırla sayfasına git
2. Eğer siparişte `Güllüayakkabı048` varsa
3. Hem `008932232669` hem de `Güllüayakkabı048` doğrulanır ✓

## 🔧 Hızlı Komutlar

```bash
# Tüm alias'ları göster
python test_alias.py

# Yeni alias ekle (web'den)
# → /barcode-alias/ sayfasına git

# Sistemde kaç alias var?
python test_alias.py --list | grep "adet"
```

## 💡 İpuçları

1. **Hızlı Test:** Terminal kullan (`python test_alias.py BARKOD`)
2. **Görsel Test:** Web arayüzünü kullan (`/barcode-alias/`)
3. **Otomatik Test:** Raf aramasında veya sipariş hazırlamada dene
4. **API Test:** curl ile endpoint'leri test et

## ✨ Şu Anda Aktif

Sisteminizde **1 adet** aktif alias var:
```
008932232669 → Güllüayakkabı048 (ekleyen: musir)
```

Her iki barkod da tüm sistemde çalışıyor! 🎉
