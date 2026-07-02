-- Trendyol müşteri soruları (Soru-Cevap entegrasyonu)
-- Idempotent: birden çok kez çalıştırılabilir.
CREATE TABLE IF NOT EXISTS trendyol_questions (
    id                      BIGINT PRIMARY KEY,
    text                    TEXT NOT NULL,
    user_name               VARCHAR(255),
    show_user_name          BOOLEAN,
    customer_id             BIGINT,
    product_name            TEXT,
    product_main_id         VARCHAR(255),
    image_url               TEXT,
    web_url                 TEXT,
    status                  VARCHAR(40),
    public                  BOOLEAN,
    reason                  TEXT,
    report_reason           TEXT,
    creation_date           TIMESTAMPTZ,
    answer_id               BIGINT,
    answer_text             TEXT,
    answer_date             TIMESTAMPTZ,
    rejected_answer_text    TEXT,
    rejected_date           TIMESTAMPTZ,
    answered_by             VARCHAR(120),
    answered_via_panel_at   TIMESTAMPTZ,
    ai_draft                TEXT,
    ai_draft_status         VARCHAR(20) DEFAULT 'none',
    ai_draft_at             TIMESTAMPTZ,
    raw_json                TEXT,
    first_seen_at           TIMESTAMPTZ DEFAULT now(),
    last_synced_at          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_trendyol_questions_status        ON trendyol_questions (status);
CREATE INDEX IF NOT EXISTS ix_trendyol_questions_creation_date ON trendyol_questions (creation_date);
CREATE INDEX IF NOT EXISTS ix_trendyol_questions_pmid          ON trendyol_questions (product_main_id);
