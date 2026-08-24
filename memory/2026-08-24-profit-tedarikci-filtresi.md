# 2026-08-24 — Kâr analizine tedarikçi filtresi

## Ne değişti
- `profit.py`: forma `tedarikci` alanı eklendi (boş = Hepsi). Seçiliyken:
  - Seçili tedarikçinin barkod kümesi `products.tedarikci_kodu` üzerinden çekilir.
  - Aktif siparişler: en az bir barkodu bu kümede olan siparişler analize girer
    (karma siparişler tam tutarıyla dahil — satır bazında bölme YOK, bilinçli).
  - İptal/iade GÖSTERİM listeleri de daraltılır; ama iptal/iade sipariş no
    kümeleri (aktiften hariç tutma) TAM kalır — yoksa başka tedarikçinin iptali
    aktif sipariş sanılırdı.
  - İade kargo maliyeti + iade gidiş kargosu yalnız filtrelenmiş iadelerden hesaplanır
    (extra_outgoing_for_returns artık len(returned_orders_temp) kullanır — filtresizken
    eski davranışla birebir aynı).
  - Dropdown listesi `products` tablosundaki distinct tedarikci_kodu/adi çiftlerinden gelir.
- `templates/profit.html`: form'a "Tedarikçi / Üretici" select'i (input CSS'i select'i de
  kapsayacak şekilde genişletildi), özet başlığına seçili tedarikçi adı eklendi.

## Neden
Kullanıcı Alissa'nın (tedarikçi: Muhammed Alissa, 7 model) hesabını ayrı görmek istiyor;
mevcut rakamlardan da şüphesi var ("doğru değil gibi") — tedarikçi bazlı süzerek kontrol
edecek. Ayrım anahtarı zaten `products.tedarikci_kodu/adi` (models.py:993).

## Dikkat
- Personel maaşı alanı doldurulursa TÜM maaş, filtrelenmiş (görünen) siparişlere dağıtılır —
  tek tedarikçi süzülürken maaşı 0 bırakmak daha doğru okuma verir.
- Tedarikçisi atanmamış ürünler hiçbir tedarikçi filtresine girmez ("Hepsi"nde görünür).

## Deploy
`git pull && systemctl restart gullupanel.service`
