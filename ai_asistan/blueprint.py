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
import shutil
import subprocess
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
    session,
)
from flask_login import current_user, login_required

ai_asistan_bp = Blueprint("ai_asistan", __name__, url_prefix="/ai-asistan")


@ai_asistan_bp.before_request
def _iki_adim_kalkani():
    """
    Derinlemesine savunma: app-level check_authentication zaten 2FA'sız
    istekleri yönlendiriyor; burada blueprint seviyesinde de kesiyoruz ki
    global kalkanda bir gedik açılsa bile AI endpoint'leri (DB erişimli!)
    2FA doğrulanmadan ASLA çalışmasın.
    """
    if not _tam_dogrulanmis_mi():
        abort(403)

# Bu dosyanın bulunduğu klasör: .mcp.json burada.
BASE_DIR = Path(__file__).resolve().parent
# İş bilgisi: Obsidian vault klasöründeki tüm notlar (yoksa IS_KURALLARI.md'ye düş).
VAULT_DIR = BASE_DIR / "vault"
IS_KURALLARI = BASE_DIR / "IS_KURALLARI.md"
# Kişiye özel sohbet geçmişi (her kullanıcı için ayrı JSON dosyası).
GECMIS_DIR = BASE_DIR / "gecmis"

# Sadece bu araca izin ver: postgres MCP'nin salt-okunur sorgu aracı.
ALLOWED_TOOLS = "mcp__gulludb__query"

# Widget'ı yalnızca bu rollere göster.
YONETICI_ROLLER = ("admin", "manager")

# Güvenlik sınırları
QUERY_TIMEOUT_SN = 90          # Claude Code'a verilen azami süre
MAX_SORU_UZUNLUK = 2000        # aşırı uzun promptları reddet
GECMIS_MAX_TUR = 12            # bağlama katılacak azami geçmiş tur (soru+cevap)


def _tam_dogrulanmis_mi() -> bool:
    """
    Kullanıcı girişi TAMAMLAMIŞ mı: login + 2FA (TOTP) doğrulaması.
    Rol bilgisi session'a 2FA'dan ÖNCE yazıldığı için tek başına role
    bakmak yeterli değil — widget/endpoint'ler 2FA ekranına sızmasın.
    """
    try:
        if not current_user.is_authenticated:
            return False
    except Exception:
        return False
    return bool(session.get("totp_verified"))


def _yonetici_mi() -> bool:
    """Aktif kullanıcı tam doğrulanmış (login + 2FA) yönetici mi?"""
    return _tam_dogrulanmis_mi() and session.get("role") in YONETICI_ROLLER


def _kullanici_id() -> str:
    """Geçmiş dosyası için güvenli kullanıcı kimliği (yalnızca alfanümerik)."""
    try:
        ham = str(current_user.get_id() or "anon")
    except Exception:
        ham = "anon"
    return "".join(ch for ch in ham if ch.isalnum()) or "anon"


def _gecmis_yolu() -> Path:
    return GECMIS_DIR / f"{_kullanici_id()}.json"


def _gecmis_oku() -> list[dict]:
    """Kullanıcının sohbet geçmişini oku (liste: {rol, metin})."""
    try:
        return json.loads(_gecmis_yolu().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _gecmis_yaz(gecmis: list[dict]) -> None:
    """Geçmişi son GECMIS_MAX_TUR*2 mesaja kırparak kaydet."""
    try:
        GECMIS_DIR.mkdir(exist_ok=True)
        kirpik = gecmis[-(GECMIS_MAX_TUR * 2):]
        _gecmis_yolu().write_text(json.dumps(kirpik, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # geçmiş yazılamazsa asistan yine çalışır


def _claude_bin() -> str | None:
    """
    'claude' çalıştırılabilirinin tam yolunu bul.
    systemd servisleri dar PATH ile çalışır ve ~/.bashrc'yi okumaz; bu yüzden
    interaktif shell'de bulunan 'claude' serviste bulunamaz. Sırayla dene:
    1) CLAUDE_BIN env değişkeni (en güvenilir — .env'de ayarla)
    2) PATH'te 'claude'
    3) Bilinen kurulum konumları
    """
    env_bin = os.getenv("CLAUDE_BIN")
    if env_bin and Path(env_bin).is_file():
        return env_bin

    found = shutil.which("claude")
    if found:
        return found

    for aday in (
        Path.home() / ".local/bin/claude",
        Path("/usr/local/bin/claude"),
        Path("/usr/bin/claude"),
        Path.home() / ".npm-global/bin/claude",
    ):
        if aday.is_file():
            return str(aday)
    return None


def _system_prompt() -> str:
    """
    İş bilgisini sistem promptu olarak yükle.
    Öncelik: Obsidian vault klasöründeki tüm .md notları (ada göre sıralı, birleştirilmiş).
    Vault yoksa IS_KURALLARI.md; o da yoksa asgari bir prompt.
    """
    if VAULT_DIR.is_dir():
        notlar = sorted(VAULT_DIR.glob("*.md"))
        parcalar = []
        for not_dosyasi in notlar:
            try:
                parcalar.append(not_dosyasi.read_text(encoding="utf-8"))
            except OSError:
                continue
        if parcalar:
            return "\n\n---\n\n".join(parcalar)

    try:
        return IS_KURALLARI.read_text(encoding="utf-8")
    except OSError:
        # Hiçbir bağlam yoksa asistan yine çalışır.
        return "Sen Güllü panelinin AI asistanısın. Soruları gulludb veritabanını sorgulayarak Türkçe yanıtla."


def _prompt_olustur(soru: str, gecmis: list[dict]) -> str:
    """Önceki konuşmayı bağlam olarak yeni sorunun önüne ekle (kişiye özel hafıza)."""
    if not gecmis:
        return soru
    satirlar = ["Önceki konuşma (bağlam):"]
    for m in gecmis[-(GECMIS_MAX_TUR * 2):]:
        etiket = "Kullanıcı" if m.get("rol") == "kullanici" else "Asistan"
        satirlar.append(f"{etiket}: {m.get('metin', '')}")
    satirlar.append(f"\nYeni soru: {soru}")
    return "\n".join(satirlar)


def _claude_calistir(soru: str, gecmis: list[dict] | None = None) -> dict:
    """
    Headless Claude Code'u çağırır ve {'ok': bool, 'cevap'/'hata': str} döner.
    gecmis verilirse önceki konuşma bağlam olarak eklenir (kişiye özel hafıza).
    """
    claude_bin = _claude_bin()
    if not claude_bin:
        return {
            "ok": False,
            "hata": "Claude Code bulunamadı. Sunucuda 'which claude' ile yolu bulup "
                    ".env'e CLAUDE_BIN=<tam yol> ekleyin (systemd dar PATH kullanır).",
        }

    # Abonelik kullanılsın diye API anahtarını bu alt-süreçten temizle.
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)

    cmd = [
        claude_bin,
        "-p", _prompt_olustur(soru, gecmis or []),
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
    """Soruyu al, doğrula, geçmişle birlikte Claude'a ilet, kaydet, JSON döndür."""
    payload = request.get_json(silent=True) or {}
    soru = (payload.get("soru") or "").strip()

    # Girdi doğrulama (sistem sınırında)
    if not soru:
        return jsonify({"ok": False, "hata": "Soru boş olamaz."}), 400
    if len(soru) > MAX_SORU_UZUNLUK:
        return jsonify({"ok": False, "hata": "Soru çok uzun."}), 400

    gecmis = _gecmis_oku()
    sonuc = _claude_calistir(soru, gecmis)

    # Başarılı cevabı kişiye özel geçmişe ekle
    if sonuc.get("ok"):
        gecmis.append({"rol": "kullanici", "metin": soru})
        gecmis.append({"rol": "asistan", "metin": sonuc["cevap"]})
        _gecmis_yaz(gecmis)

    return jsonify(sonuc)


@ai_asistan_bp.route("/gecmis", methods=["GET"])
@login_required
def gecmis():
    """Aktif kullanıcının sohbet geçmişini döndür (widget açılışında yüklenir)."""
    return jsonify({"ok": True, "gecmis": _gecmis_oku()})


@ai_asistan_bp.route("/temizle", methods=["POST"])
@login_required
def temizle():
    """Aktif kullanıcının sohbet geçmişini sil."""
    try:
        _gecmis_yolu().unlink(missing_ok=True)
    except OSError:
        pass
    return jsonify({"ok": True})


@ai_asistan_bp.after_app_request
def _widget_enjekte(response):
    """
    Her HTML sayfasının sonuna, kullanıcı yönetici ise AI widget'ını ekle.
    Böylece 66 şablonu tek tek düzenlemeye gerek kalmaz — tek kaynak, tüm sayfalar.
    """
    try:
        if not _yonetici_mi():
            return response
        ctype = response.headers.get("Content-Type", "")
        if "text/html" not in ctype or response.direct_passthrough:
            return response

        govde = response.get_data(as_text=True)
        if 'id="aiw-wrap"' in govde:
            return response

        # SON </body>'den önce enjekte et. İlk </body> sayfanın inline JS'i içinde
        # (ör. yazdırma fonksiyonundaki "</body></html>" string'i) olabilir; oraya
        # enjekte etmek script'i bozar. rfind ile gerçek kapanış etiketini hedefliyoruz.
        idx = govde.rfind("</body>")
        if idx == -1:
            return response

        widget = render_template("includes/ai_widget.html")
        response.set_data(govde[:idx] + widget + "\n" + govde[idx:])
    except Exception:
        current_app.logger.exception("AI widget enjeksiyonu başarısız")
    return response
