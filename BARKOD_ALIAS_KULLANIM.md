# 🔖 Barkod Alias Sistemi

## 📋 Özet

Bu sistem, **birden fazla barkodun aynı ürünü göstermesini** sağlar. Raflara farklı barkodlar yapıştırdıysanız, bunları sistem içindeki ana barkoda bağlayabilirsiniz.

## 🎯 Kullanım Senaryosu

**Sorun:**
- Aynı model, aynı renk, aynı ürün ama farklı barkodlarla rafta
- Yeni barkod yapıştırmak istemiyorsunuz
- Sistem tek barkod kullanıyor

**Çözüm:**
Alias sistemi ile alternatif barkodları ana barkoda bağlayın!

## 🚀 Nasıl Kullanılır?

### 1️⃣ Migration'ı Çalıştırın

İlk kurulumda tabloyu oluşturun:

```bash
python migrate_barcode_alias.py
```

### 2️⃣ Alias Ekleme

**Web Arayüzü:**
- `/barcode-alias/` adresine gidin
- Alternatif barkod (raflardaki) ve ana barkod (sistemdeki) girin
- "Kaydet" butonuna tıklayın

**Örnek:**
```
Alternatif Barkod (Alias): ABC123
Ana Barkod (Gerçek):       XYZ789
Not:                       Eski etiket
```

Artık `ABC123` barkodunu okuttuğunuzda sistem `XYZ789` olarak işler!

### 3️⃣ Otomatik Çalışma

Alias ekledikten sonra:

✅ **Raf Sistemi:** Her iki barkod da aynı ürünü bulur  
✅ **Sipariş Hazırlama:** Her iki barkod da doğrulama geçer  
✅ **Stok İşlemleri:** Otomatik ana barkod kullanılır  

## 📍 Özellikler

### ✨ Tam Entegrasyon

- `raf_sistemi.py` - Barkod aramalarda alias desteği
- `siparis_hazirla.py` - Paketleme doğrulamada alias desteği
- Tüm stok işlemleri otomatik normalize edilir

### 🔧 Yönetim

- Web arayüzü ile kolay ekleme/silme
- Ana barkoda göre gruplu görüntüleme
- Not ekleme özelliği
- Kimlerin eklediğini görme

### 🛡️ Güvenlik

- Login gerekli (sadece yetkili kullanıcılar)
- Silme onay penceresi
- Alias çakışma kontrolü

## 📂 Dosya Yapısı

```
models.py                    # BarcodeAlias model tanımı
barcode_alias_helper.py      # normalize_barcode() ve yardımcı fonksiyonlar
barcode_alias_routes.py      # Web arayüzü route'ları
templates/barcode_alias.html # Yönetim sayfası
migrate_barcode_alias.py     # Veritabanı migration scripti
```

## 🔥 API Kullanımı

### normalize_barcode()

```python
from barcode_alias_helper import normalize_barcode

# Alias ise ana barkoda çevirir, değilse kendisini döner
main_barcode = normalize_barcode('ABC123')  # -> 'XYZ789'
```

### add_alias()

```python
from barcode_alias_helper import add_alias

result = add_alias(
    alias_barcode='ABC123',
    main_barcode='XYZ789',
    created_by='musir',
    note='Eski etiket'
)

if result['success']:
    print(result['message'])  # "Alias eklendi: ABC123 -> XYZ789"
```

### get_alias_info()

```python
from barcode_alias_helper import get_alias_info

info = get_alias_info('ABC123')
# {
#     'is_alias': True,
#     'main_barcode': 'XYZ789',
#     'aliases': [],
#     'note': 'Eski etiket'
# }
```

## ⚠️ Önemli Notlar

1. **Ana Barkod Gerçek Olmalı:** Sistemde kayıtlı bir ürün barkodu kullanın
2. **Benzersizlik:** Bir alias sadece bir ana barkoda bağlanabilir
3. **Sonsuz Döngü Yok:** Alias'lar zincirleme çalışmaz (A->B->C değil, sadece A->C)
4. **Silme Etkisi:** Alias sildiğinizde raflardan fiziksel olarak kaldırmanız gerekebilir

## 📊 Örnek Kullanımlar

### Durum 1: Eski Etiketler
```
Raf etiketleri: OLD001, OLD002, OLD003
Sistemde:       NEW999

Çözüm:
OLD001 -> NEW999
OLD002 -> NEW999
OLD003 -> NEW999
```

### Durum 2: Tedarikçi Farklılığı
```
Tedarikçi A:    SUP-A-100
Tedarikçi B:    SUP-B-200
Sistemde:       MAIN-100

Çözüm:
SUP-A-100 -> MAIN-100
SUP-B-200 -> MAIN-100
```

## 🔍 Sorun Giderme

**Alias çalışmıyor:**
- Migration çalıştırıldı mı? (`python migrate_barcode_alias.py`)
- Blueprint register edildi mi? (`routes/__init__.py`)
- Önbellek temizlendi mi? (Sunucuyu restart edin)

**Alias ekleme hatası:**
- Ana barkod sistemde var mı?
- Alias zaten başka bir ürüne bağlı mı?
- Barkodlar boşluksuz yazıldı mı?

## 📝 Geliştirme

Yeni bir yerde alias desteği eklemek için:

```python
from barcode_alias_helper import normalize_barcode

# Eski kod
product = Product.query.filter_by(barcode=user_barcode).first()

# Yeni kod (alias destekli)
normalized = normalize_barcode(user_barcode)
product = Product.query.filter_by(barcode=normalized).first()
```

## 🎉 Tamamlandı!

Artık raflardaki eski barkodları değiştirmeden, sisteminizde tek bir ürün olarak yönetebilirsiniz!

**Yönetim Paneli:** `/barcode-alias/`
