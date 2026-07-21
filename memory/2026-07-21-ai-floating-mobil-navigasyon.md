# AI floating butonu ve mobil ana sayfa navigasyonu

## Değişiklik

- Global AI asistanı widget'ı sağ alt köşeye alındı; mobilde safe-area boşluklarına ve dinamik viewport yüksekliğine uyarlandı.
- Ana sayfadaki mobil navigasyon sabit alt şeritten normal akışta iki sütunlu grid'e çevrildi.
- Uzun buton etiketlerinin satırı büyütmesine izin verilerek buton ve içerik çakışması engellendi.

## Neden

Sabit alt navigasyon içeriğin ve AI butonunun üzerine biniyordu. Navigasyonu belge akışına almak, farklı mobil genişliklerde hesaplanamayan sabit bir alt boşluğa bağımlılığı kaldırdı.
