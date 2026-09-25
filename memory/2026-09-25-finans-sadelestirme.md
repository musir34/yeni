# 2026-09-25 — Finans adları ve günlük harcama formu

Kullanıcının 1. ve 4. öneri talebi uygulandı:
- Küçük Gider → Günlük Harcamalar; Ana Gider → Düzenli Ödemeler. Menü, panel, rapor, tanımlar, ödeme penceresi ve ortak işlem etiketleri güncellendi.
- Harcama formunda tutar/açıklama öne alındı; ödeme hesabı ve zorunlu kategori görünür kaldı. Tarih (bugün varsayılan) ve isteğe bağlı hazır harcama açılır ayrıntılara taşındı.
- Mevcut kategori API'si ile formdan ayrılmadan kategori oluşturma ve otomatik seçme eklendi. Kategorisiz başlangıç, hata mesajları, yinelenen tıklama ve eski hazır-harcama yanıtları ele alındı.
- Hesap kuralları, veritabanı şeması ve kayıt türü kodları değişmedi.

Doğrulama: 12 finans şablonunun Jinja sözdizimi, kategorili/kategorisiz form render kontrolü, render edilen JavaScript için node --check, finans_service.py Python sözdizimi ve git diff --check geçti. Canlı uygulama veya tarayıcı testi yapılmadı.
