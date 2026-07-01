-- ============================================================
-- AI Asistanı için SALT-OKUNUR PostgreSQL rolü
-- ============================================================
-- Bu rol paneldeki AI asistanının veritabanına bağlanması için.
-- AMAÇ: Her tabloyu OKUYABİLİR, ama HİÇBİR ŞEY yazamaz/silemez/değiştiremez.
--
-- Sunucuda (138.199.218.72) çalıştır:
--   psql "postgresql://musir:<PAROLA>@138.199.218.72:5432/gulludb" -f create_readonly_role.sql
--
-- Sonra ai_ro_password'ü güçlü bir parolayla değiştir ve .env'e AI_DB_URL olarak koy.
-- ============================================================

-- 1) Rolü oluştur; ZATEN VARSA şifreyi/LOGIN'i kesinleştir (idempotent).
--    .env'deki AI_DB_URL şifresiyle BİREBİR AYNI olmalı.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_readonly') THEN
        CREATE ROLE ai_readonly LOGIN PASSWORD 'DEGISTIR_guclu_parola_buraya';
    ELSE
        ALTER ROLE ai_readonly LOGIN PASSWORD 'DEGISTIR_guclu_parola_buraya';
    END IF;
END
$$;

-- 2) Veritabanına ve şemaya bağlanma izni
GRANT CONNECT ON DATABASE gulludb TO ai_readonly;
GRANT USAGE ON SCHEMA public TO ai_readonly;

-- 3) Mevcut tüm tablolarda SADECE SELECT
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ai_readonly;

-- 4) Bundan sonra oluşturulacak tablolarda da otomatik SELECT
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO ai_readonly;

-- 5) GÜVENLİK: Bu rolün asla yazma yapamayacağından emin ol
--    (varsayılan olarak yok ama açıkça REVOKE ediyoruz)
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON ALL TABLES IN SCHEMA public FROM ai_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLES FROM ai_readonly;

-- 6) Sorgu maliyetini sınırla: bu rol için ifade zaman aşımı (30 sn)
--    Kaçak/ağır sorgular sunucuyu kilitlemesin.
ALTER ROLE ai_readonly SET statement_timeout = '30s';

-- 7) Doğrulama: rolün yetkilerini göster
--    (yalnızca SELECT görünmeli)
SELECT grantee, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'ai_readonly'
ORDER BY table_name, privilege_type
LIMIT 20;
