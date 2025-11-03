-- StockPushLog tablosunu oluştur
-- Bu tablo Trendyol'a gönderilen stok güncellemelerini loglar

CREATE TABLE IF NOT EXISTS stock_push_log (
    id SERIAL PRIMARY KEY,
    push_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_items INTEGER NOT NULL DEFAULT 0,
    total_quantity INTEGER NOT NULL DEFAULT 0,
    reserved_quantity INTEGER NOT NULL DEFAULT 0,
    batch_count INTEGER NOT NULL DEFAULT 0,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error_message TEXT,
    duration_seconds FLOAT
);

-- Index ekle (zaman bazlı sorgular için)
CREATE INDEX IF NOT EXISTS ix_stock_push_log_push_time ON stock_push_log(push_time DESC);

-- Tablo oluşturuldu mu kontrol
SELECT COUNT(*) as table_exists 
FROM information_schema.tables 
WHERE table_name = 'stock_push_log';

-- İlk 5 kaydı göster (test için)
SELECT * FROM stock_push_log ORDER BY push_time DESC LIMIT 5;
