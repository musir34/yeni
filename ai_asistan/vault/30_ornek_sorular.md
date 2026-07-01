# Örnek Sorular ve Yaklaşım

- **"Bugün kaç sipariş geldi?"** → orders tablosunda bugünün tarih aralığında COUNT.
- **"En çok satan 5 model?"** → sipariş satırlarını modele göre grupla, adet topla, DESC LIMIT 5.
- **"X modelinin stoğu ne?"** → stok tablosunda model koduna göre bak.
- **"Kaç sipariş gecikti?"** → teslim tarihi < now() ve statü Shipped değil.
- **"Bu ayki ciro?"** → siparişlerin tutarını ay aralığında topla.

> Kullanıcı yeni soru tipleri sorup doğru cevap alamazsa, doğru yaklaşımı buraya örnek olarak ekle.
