-- CentralStock last_push_date Kolonu Ekleme
-- Tarih: 2025-11-03

-- Kolon ekle
ALTER TABLE central_stock 
ADD COLUMN IF NOT EXISTS last_push_date TIMESTAMPTZ;

-- Index ekle (performans için)
CREATE INDEX IF NOT EXISTS ix_central_stock_last_push_date 
ON central_stock(last_push_date DESC NULLS LAST);

-- Kontrol sorgusu
SELECT 
    COUNT(*) as toplam_urun,
    COUNT(last_push_date) as gonderilmis_urun,
    COUNT(*) - COUNT(last_push_date) as henuz_gonderilmemis
FROM central_stock;

-- Örnek veriler
SELECT 
    barcode,
    qty,
    updated_at,
    last_push_date,
    CASE 
        WHEN last_push_date IS NULL THEN 'Henüz gönderilmedi'
        WHEN last_push_date > NOW() - INTERVAL '1 hour' THEN 'Son 1 saatte'
        WHEN last_push_date > NOW() - INTERVAL '1 day' THEN 'Bugün'
        ELSE 'Daha eski'
    END as durum
FROM central_stock
ORDER BY last_push_date DESC NULLS LAST
LIMIT 20;
