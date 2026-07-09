# CLAUDE.md — Güllü Panel Çalışma İlkeleri

Bu proje büyük ve iç içe geçmiş bir sistem (stok ledger, stok senkron, pazaryeri
statüleri, sipariş yaşam döngüsü, saat dilimi). Küçük bir dokunuş uzaktaki bir yeri
bozabilir. Bu yüzden aşağıdaki iki ilke ZORUNLUDUR.
(Kaynak: Andrej Karpathy'nin LLM kodlama gözlemleri — yalnızca "cerrahi + önce-düşün"
kısmı alındı; "her şeyi minimal tut / TDD ile çöz" kısmı bu projeye uygun değil, alınmadı.)

## 1. Önce Düşün — Belirsizse Sor

- Kod yazmadan önce varsayımlarını AÇIKÇA söyle.
- İstek belirsizse veya birden fazla yorumu varsa, tahmin edip yazma — SOR.
  Yanlış yeri düzeltip sonra geri almaktansa, baştan bir soru sor.
- Değiştirmeden önce ilgili akışı (ledger, senkron, statü geçişleri) gerçekten
  anla; `file:line` kanıtı olmadan "sebep bu" deme.
- Ödünleşim varsa seçenekleri değil, bir öneriyi sun; ama kararı etkileyen bir
  belirsizlik varsa kullanıcıya bırak.

## 2. Cerrahi Değişiklik

- YALNIZCA isteğin gerektirdiği kodu değiştir. Çalışan kodu "iyileştirmek" için
  refactor etme.
- Mevcut stili, isimlendirmeyi ve deseni koru — çevre kod nasılsa öyle yaz.
- Diff'teki her satır doğrudan isteğe bağlanabilmeli; "bu arada şunu da düzelttim"
  yok.
- Yalnızca KENDİ eklediğin değişikliğin ürettiği ölü kodu temizle; önceden var
  olana dokunma.
- DB/şema değişikliği additive olsun (migration gerekiyorsa açıkça belirt);
  geriye dönük uyumu koru.

## Ek proje kuralları
- Her cevabın sonuna `Güllü Shoes🌹` imzası.
- Değişiklikten sonra: değişeni/nedenini `memory/` klasörüne kısa not olarak yaz.
- Deploy kullanıcıda: kod değişiklikleri `git pull && systemctl restart gullupanel.service`.
