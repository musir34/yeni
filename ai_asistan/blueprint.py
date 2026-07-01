"""
AI Asistanı — Flask blueprint.

Panel içindeki sohbet kutusundan gelen soruyu, sunucuda headless çalışan
Claude Code'a (Max aboneliğiyle giriş yapılmış) iletir. Claude Code, salt-okunur
PostgreSQL MCP üzerinden veritabanını sorgulayıp Türkçe cevap döner.

GÜVENLİK:
- Terminal/keyfi komut YOK. Sadece 'sor' endpoint'i var.
- Claude Code yalnızca postgres MCP'nin salt-okunur 'query' aracını kullanabilir
  (--allowedTools ile beyaz listelenmiş).
- Veritabanı bağlantısı ai_readonly rolüyle → yazma fiziksel olarak imkânsız.
- login_required → sadece panele girmiş kullanıcılar sorabilir.
- ANTHROPIC_API_KEY ortamdan TEMİZLENİR → abonelik kullanılır, API faturası oluşmaz.
"""
import json
import os
import subprocess
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

ai_asistan_bp = Blueprint("ai_asistan", __name__, url_prefix="/ai-asistan")

# Bu dosyanın bulunduğu klasör: .mcp.json ve IS_KURALLARI.md burada.
BASE_DIR = Path(__file__).resolve().parent
IS_KURALLARI = BASE_DIR / "IS_KURALLARI.md"

# Sadece bu araca izin ver: postgres MCP'nin salt-okunur sorgu aracı.
ALLOWED_TOOLS = "mcp__gulludb__query"

# Güvenlik sınırları
QUERY_TIMEOUT_SN = 90          # Claude Code'a verilen azami süre
MAX_SORU_UZUNLUK = 2000        # aşırı uzun promptları reddet


def _system_prompt() -> str:
    """İş kuralları dosyasını sistem promptu olarak yükle."""
    try:
        return IS_KURALLARI.read_text(encoding="utf-8")
    except OSError:
        # Dosya yoksa asistan yine çalışır, sadece bağlam olmadan.
        return "Sen Güllü panelinin AI asistanısın. Soruları gulludb veritabanını sorgulayarak Türkçe yanıtla."


def _claude_calistir(soru: str) -> dict:
    """
    Headless Claude Code'u çağırır ve {'ok': bool, 'cevap'/'hata': str} döner.
    """
    # Abonelik kullanılsın diye API anahtarını bu alt-süreçten temizle.
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)

    cmd = [
        "claude",
        "-p", soru,
        "--append-system-prompt", _system_prompt(),
        "--allowedTools", ALLOWED_TOOLS,
        "--output-format", "json",
    ]

    try:
        sonuc = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),          # .mcp.json buradan yüklenir
            env=env,
            capture_output=True,
            text=True,
            timeout=QUERY_TIMEOUT_SN,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "hata": "Sorgu zaman aşımına uğradı. Lütfen soruyu sadeleştirin."}
    except FileNotFoundError:
        return {"ok": False, "hata": "Claude Code sunucuda kurulu değil (PATH'te 'claude' yok)."}

    if sonuc.returncode != 0:
        return {"ok": False, "hata": f"Asistan hatası: {sonuc.stderr[:500] or 'bilinmeyen hata'}"}

    # --output-format json → {"result": "...", ...} bekleniyor
    try:
        data = json.loads(sonuc.stdout)
        cevap = data.get("result") or data.get("text") or ""
    except (json.JSONDecodeError, AttributeError):
        cevap = sonuc.stdout.strip()

    if not cevap:
        return {"ok": False, "hata": "Asistandan boş cevap geldi."}

    return {"ok": True, "cevap": cevap}


@ai_asistan_bp.route("/", methods=["GET"])
@login_required
def sayfa():
    """Sohbet kutusu sayfası."""
    return render_template("ai_asistan.html")


@ai_asistan_bp.route("/sor", methods=["POST"])
@login_required
def sor():
    """Soruyu al, doğrula, Claude Code'a ilet, cevabı JSON döndür."""
    payload = request.get_json(silent=True) or {}
    soru = (payload.get("soru") or "").strip()

    # Girdi doğrulama (sistem sınırında)
    if not soru:
        return jsonify({"ok": False, "hata": "Soru boş olamaz."}), 400
    if len(soru) > MAX_SORU_UZUNLUK:
        return jsonify({"ok": False, "hata": "Soru çok uzun."}), 400

    return jsonify(_claude_calistir(soru))
