"""
Trendyol soruları için AI cevap taslağı üretimi.

ai_asistan altyapısını (headless Claude Code, Max aboneliği, salt-okunur
postgres MCP) yeniden kullanır. Taslak asla otomatik gönderilmez — panelde
insan onayından geçer.
"""
import json
import logging
import os
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_asistan.blueprint import _claude_bin, BASE_DIR as AI_ASISTAN_DIR

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
KURALLAR_MD = BASE_DIR / "CEVAP_KURALLARI.md"
ALLOWED_TOOLS = "mcp__gulludb__query"  # salt-okunur DB (opsiyonel; stok zaten prompta gömülü)
DRAFT_TIMEOUT_SN = 120
FALLBACK_PROMPT = "Sen Güllü Shoes'un Trendyol müşteri sorularına kısa, kibar Türkçe cevap taslağı yazan asistanısın. Sadece cevap metnini yaz."


def _kurallar() -> str:
    """Sistem promptu: cevap kuralları + Obsidian vault'taki bilgi notları."""
    try:
        kurallar = KURALLAR_MD.read_text(encoding="utf-8")
    except OSError:
        kurallar = FALLBACK_PROMPT
    from trendyol_qna.qna_notes import load_vault_notes
    notlar = load_vault_notes()
    if notlar:
        kurallar += (
            "\n\n---\n\n# Bilgi Bankası (geçmiş cevaplar ve notlar)\n"
            "Aşağıdaki notlar mağazanın GERÇEK geçmiş cevaplarından derlendi. "
            "Üslubu ve bilgileri örnek al; ama STOK için her zaman sana verilen "
            "CANLI STOK verisini esas al (geçmiş 'üretimi sonlandı' notu bugün geçersiz olabilir).\n\n"
            + notlar
        )
    return kurallar


def _draft_prompt(row, stok_bilgisi: str) -> str:
    return (
        f"Ürün: {row.product_name or 'bilinmiyor'}\n"
        f"Model kodu: {row.product_main_id or 'bilinmiyor'}\n"
        f"CANLI STOK: {stok_bilgisi}\n\n"
        f"Müşteri sorusu:\n{row.text}\n\n"
        "Bu soruya kurallara uygun, Trendyol'a gönderilmeye hazır TEK bir cevap taslağı yaz."
    )


def _run_claude(prompt: str) -> str | None:
    """Headless Claude çağır, taslak metnini döndür (hata → None)."""
    claude_bin = _claude_bin()
    if not claude_bin:
        logger.warning("[QNA-AI] claude binary bulunamadı (CLAUDE_BIN ayarlayın)")
        return None

    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)  # abonelik kullanılsın, API faturası oluşmasın

    cmd = [
        claude_bin,
        "-p", prompt,
        "--append-system-prompt", _kurallar(),
        "--allowedTools", ALLOWED_TOOLS,
        "--output-format", "json",
    ]
    try:
        sonuc = subprocess.run(
            cmd,
            cwd=str(AI_ASISTAN_DIR),  # .mcp.json (gulludb) buradan yüklenir
            env=env,
            capture_output=True,
            text=True,
            timeout=DRAFT_TIMEOUT_SN,
        )
    except subprocess.TimeoutExpired:
        logger.warning("[QNA-AI] taslak üretimi zaman aşımı")
        return None
    except OSError as e:
        logger.warning("[QNA-AI] claude çalıştırılamadı: %s", e)
        return None

    if sonuc.returncode != 0:
        logger.warning("[QNA-AI] claude hata: %s", (sonuc.stderr or "")[:300])
        return None
    try:
        data = json.loads(sonuc.stdout)
        text = (data.get("result") or data.get("text") or "").strip()
    except (json.JSONDecodeError, AttributeError):
        text = (sonuc.stdout or "").strip()
    return text or None


def generate_draft(question_id: int) -> dict:
    """
    Tek soru için taslak üret ve kaydet (senkron; app context İÇİNDE çağrılmalı).
    Dönen: {'ok': bool, 'taslak'/'hata': str}
    """
    from models import db, TrendyolQuestion
    from trendyol_qna.qna_service import stock_context, ANSWER_MAX

    row = db.session.get(TrendyolQuestion, question_id)
    if not row:
        return {"ok": False, "hata": "Soru bulunamadı."}

    # Çifte üretim koruması: zaten üretiliyorsa (ve takılı kalmadıysa) atla.
    # ai_draft_at pending'e geçerken de damgalanır; 5 dk'yı aşan pending
    # çökmüş sayılır ve yeniden üretime izin verilir.
    if row.ai_draft_status == "pending" and row.ai_draft_at:
        ts = row.ai_draft_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - ts < timedelta(minutes=5):
            return {"ok": False, "hata": "Taslak zaten üretiliyor."}

    row.ai_draft_status = "pending"
    row.ai_draft_at = datetime.now(timezone.utc)
    db.session.commit()

    taslak = _run_claude(_draft_prompt(row, stock_context(row.product_main_id)))
    if taslak:
        row.ai_draft = taslak[:ANSWER_MAX]
        row.ai_draft_status = "ready"
        row.ai_draft_at = datetime.now(timezone.utc)
        db.session.commit()
        return {"ok": True, "taslak": row.ai_draft}

    row.ai_draft_status = "failed"
    db.session.commit()
    return {"ok": False, "hata": "AI taslak üretilemedi (sunucu loglarına bakın)."}


def generate_drafts_async(question_ids: list[int]) -> None:
    """Yeni sorular için taslakları arka plan thread'inde sırayla üret."""
    if not question_ids:
        return

    def _worker():
        from app import app
        with app.app_context():
            for qid in question_ids:
                try:
                    generate_draft(qid)
                except Exception:
                    logger.exception("[QNA-AI] taslak hatası (soru %s)", qid)

    t = threading.Thread(target=_worker, name="qna-ai-draft", daemon=True)
    t.start()
