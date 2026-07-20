"""
AI Asistanı — Flask blueprint.

Panel içindeki sohbet kutusundan gelen soruyu, sunucuda headless çalışan
Claude Code'a (Max aboneliğiyle giriş yapılmış) iletir. Claude Code, salt-okunur
PostgreSQL MCP üzerinden veritabanını sorgulayıp Türkçe cevap döner.

MİMARİ (2026-07-10 revizyonu):
- Çoklu sohbet: kullanıcı başına ai_sohbet/ai_mesaj tabloları (JSON dosya yerine DB).
- ASENKRON cevap: /sor mesajı DB'ye yazar, Claude'u arka plan thread'inde başlatır
  ve anında döner; frontend /durum/<id> ile yoklar. Böylece gunicorn worker'ı
  90+ sn bloklanmaz → worker timeout kaynaklı "sunucu hatası" (502) biter.
- Bağlam: geçmişi prompta metin olarak yapıştırmak yerine claude --resume
  <session_id> ile gerçek oturum devamlılığı (sohbet başına session_id saklanır).
- Model: opus (premium cevap kalitesi).

GÜVENLİK:
- Terminal/keyfi komut YOK. Sadece 'sor' endpoint'i var.
- Claude Code yalnızca postgres MCP'nin salt-okunur 'query' aracını kullanabilir
  (--allowedTools ile beyaz listelenmiş).
- Veritabanı bağlantısı ai_readonly rolüyle → yazma fiziksel olarak imkânsız.
- login_required → sadece panele girmiş kullanıcılar sorabilir.
- Sohbet erişiminde sahiplik kontrolü (başkasının sohbet_id'si → 404).
- ANTHROPIC_API_KEY ortamdan TEMİZLENİR → abonelik kullanılır, API faturası oluşmaz.
"""
import json
import os
import shutil
import subprocess
import threading
from datetime import datetime, timedelta
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

from models import db, AiSohbet, AiMesaj

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
# Eski (dosya tabanlı) sohbet geçmişi — ilk listelemede DB'ye bir kez içeri alınır.
GECMIS_DIR = BASE_DIR / "gecmis"

# Sadece bu araca izin ver: postgres MCP'nin salt-okunur sorgu aracı.
ALLOWED_TOOLS = "mcp__gulludb__query"

# Widget'ı yalnızca bu rollere göster.
YONETICI_ROLLER = ("admin", "manager")

# Güvenlik sınırları
QUERY_TIMEOUT_SN = 240         # Claude Code'a verilen azami süre (asenkron: worker bloklanmaz)
MAX_SORU_UZUNLUK = 2000        # aşırı uzun promptları reddet
MAX_SOHBET_LISTE = 50          # geçmiş listesinde gösterilecek azami sohbet
BASLIK_UZUNLUK = 60            # sohbet başlığı = ilk sorunun ilk N karakteri

CLAUDE_MODEL = "opus"          # premium cevap kalitesi (abonelik dahilinde)

# Hangi AI motoru çalışsın: 'claude' (varsayılan) veya 'codex'. .env ile değiştirilir;
# sorun çıkarsa AI_MOTOR=claude ile tek satırda geri dönülür.
AI_MOTOR = (os.getenv("AI_MOTOR") or "claude").strip().lower()
# Boş bırakılırsa codex kendi yapılandırmasındaki varsayılan modeli kullanır.
CODEX_MODEL = (os.getenv("CODEX_MODEL") or "").strip()


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
    """Sohbet sahipliği için güvenli kullanıcı kimliği (yalnızca alfanümerik)."""
    try:
        ham = str(current_user.get_id() or "anon")
    except Exception:
        ham = "anon"
    return "".join(ch for ch in ham if ch.isalnum()) or "anon"


def _sohbet_getir(sohbet_id: int) -> AiSohbet:
    """Sohbeti sahiplik kontrolüyle getir; başkasının sohbeti → 404."""
    sohbet = db.session.get(AiSohbet, sohbet_id)
    if sohbet is None or sohbet.kullanici != _kullanici_id():
        abort(404)
    return sohbet


def _eski_json_ice_al(uid: str) -> None:
    """
    Eski dosya tabanlı geçmişi (gecmis/<uid>.json) bir kez DB'ye taşı.
    Başarılı taşımada dosya .imported uzantısına alınır; hata asistanı durdurmaz.
    """
    eski = GECMIS_DIR / f"{uid}.json"
    if not eski.is_file():
        return
    try:
        mesajlar = json.loads(eski.read_text(encoding="utf-8"))
        if mesajlar:
            sohbet = AiSohbet(kullanici=uid, baslik="Eski sohbet")
            db.session.add(sohbet)
            db.session.flush()
            for m in mesajlar:
                db.session.add(AiMesaj(
                    sohbet_id=sohbet.id,
                    rol=m.get("rol") or "asistan",
                    metin=m.get("metin") or "",
                    durum="hazir",
                ))
            db.session.commit()
        eski.rename(eski.with_suffix(".json.imported"))
    except Exception:
        db.session.rollback()
        current_app.logger.exception("[AI-ASISTAN] eski JSON geçmişi içeri alınamadı")


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


def _codex_bin() -> str | None:
    """
    'codex' çalıştırılabilirinin tam yolunu bul (_claude_bin ile aynı mantık).
    """
    env_bin = os.getenv("CODEX_BIN")
    if env_bin and Path(env_bin).is_file():
        return env_bin

    found = shutil.which("codex")
    if found:
        return found

    for aday in (
        Path.home() / ".local/bin/codex",
        Path("/usr/local/bin/codex"),
        Path("/usr/bin/codex"),
        Path.home() / ".npm-global/bin/codex",
    ):
        if aday.is_file():
            return str(aday)
    return None


def _codex_env() -> dict:
    """
    Codex alt süreci için ortam: abonelik (codex login) kullanılsın diye
    OPENAI_API_KEY temizlenir; üst süreçten sızan CODEX_* oturum/sandbox
    değişkenleri de (CODEX_BIN, CODEX_HOME hariç) alt sürecin sandbox'ını
    bozmasın diye atılır.
    """
    return {
        k: v for k, v in os.environ.items()
        if not (k.startswith("OPENAI")
                or (k.startswith("CODEX") and k not in ("CODEX_BIN", "CODEX_HOME")))
    }


def _codex_ciktisi_coz(stdout: str) -> tuple[str, str | None]:
    """
    'codex exec --json' JSONL akışını çöz → (cevap, thread_id).
    İlgilendiğimiz olaylar: thread.started (oturum kimliği) ve
    item.completed/agent_message (asistan metni; sonuncusu esas alınır).
    """
    cevap = ""
    thread_id = None
    for satir in stdout.splitlines():
        satir = satir.strip()
        if not satir.startswith("{"):
            continue
        try:
            olay = json.loads(satir)
        except json.JSONDecodeError:
            continue
        tur = olay.get("type")
        if tur == "thread.started":
            thread_id = olay.get("thread_id") or thread_id
        elif tur == "item.completed":
            item = olay.get("item") or {}
            if item.get("type") == "agent_message" and item.get("text"):
                cevap = item["text"]
    return cevap.strip(), thread_id


def _codex_calistir(soru: str, sistem_prompt: str, timeout_sn: int,
                    resume_session_id: str | None = None,
                    cwd: Path | None = None) -> dict:
    """
    Headless Codex CLI'yi çağırır; _claude_calistir ile AYNI sözleşmeyi döner:
    {'ok': bool, 'cevap'/'hata': str, 'session_id': str|None}

    Claude'dan farkları (codex 0.144):
    - '--append-system-prompt' yok → sistem promptu ilk soruya önekleniyor
      (resume'da gerekmez, oturumda zaten var).
    - Araç bazlı beyaz liste ('--allowedTools') yok → yazma engeli sandbox
      (read-only) ve DB tarafındaki ai_readonly rolüyle sağlanır.
    - Oturum sürdürme ayrı alt komut: 'codex exec resume <thread_id>'; bu alt
      komut '-s' kabul etmediği için sandbox/onay '-c' ile veriliyor.
    """
    codex_bin = _codex_bin()
    if not codex_bin:
        return {
            "ok": False, "session_id": None,
            "hata": "Codex CLI bulunamadı. Sunucuda 'which codex' ile yolu bulup "
                    ".env'e CODEX_BIN=<tam yol> ekleyin (systemd dar PATH kullanır).",
        }

    cmd = [codex_bin, "exec"]
    if resume_session_id:
        cmd += ["resume", resume_session_id, soru]
    else:
        cmd += [f"{sistem_prompt}\n\n---\n\n{soru}"]
    cmd += [
        "--json",
        "--skip-git-repo-check",
        "-c", 'sandbox_mode="read-only"',
        "-c", 'approval_policy="never"',
    ]
    if CODEX_MODEL:
        cmd += ["-m", CODEX_MODEL]

    try:
        sonuc = subprocess.run(
            cmd,
            cwd=str(cwd or BASE_DIR),
            env=_codex_env(),
            capture_output=True,
            text=True,
            timeout=timeout_sn,
            stdin=subprocess.DEVNULL,   # aksi halde codex prompt'u stdin'den bekler
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "session_id": None,
                "hata": "Sorgu zaman aşımına uğradı. Lütfen soruyu sadeleştirin."}
    except OSError as e:
        return {"ok": False, "session_id": None,
                "hata": f"Codex çalıştırılamadı: {e}"}

    if sonuc.returncode != 0:
        import logging
        logging.getLogger(__name__).error(
            "[AI-ASISTAN] codex rc=%s resume=%s stderr=%r stdout=%r",
            sonuc.returncode, bool(resume_session_id),
            (sonuc.stderr or "")[:500], (sonuc.stdout or "")[:500],
        )
        detay = (sonuc.stderr or "").strip() or (sonuc.stdout or "").strip()[:500]
        return {"ok": False, "session_id": None,
                "hata": f"Asistan hatası: {detay or 'bilinmeyen hata'}"}

    cevap, thread_id = _codex_ciktisi_coz(sonuc.stdout or "")
    if not cevap:
        return {"ok": False, "session_id": None, "hata": "Asistandan boş cevap geldi."}
    return {"ok": True, "cevap": cevap, "session_id": thread_id}


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


def _claude_calistir(soru: str, resume_session_id: str | None = None) -> dict:
    """
    Headless Claude Code'u çağırır.
    Dönen: {'ok': bool, 'cevap'/'hata': str, 'session_id': str|None}
    resume_session_id verilirse oturum --resume ile sürdürülür (tam bağlam);
    resume başarısız olursa (oturum dosyası silinmiş vb.) taze oturumla
    bir kez daha denenir — kullanıcıya hata yansımaz, sadece bağlam tazelenir.
    """
    claude_bin = _claude_bin()
    if not claude_bin:
        return {
            "ok": False, "session_id": None,
            "hata": "Claude Code bulunamadı. Sunucuda 'which claude' ile yolu bulup "
                    ".env'e CLAUDE_BIN=<tam yol> ekleyin (systemd dar PATH kullanır).",
        }

    # Abonelik kullanılsın ve üst süreçten sızan oturum değişkenleri
    # (CLAUDECODE, CLAUDE_CODE_SSE_PORT vb.) nested-session/401 hatasına yol
    # açmasın diye TÜM Anthropic/Claude env'lerini temizle (CLAUDE_BIN hariç).
    env = {
        k: v for k, v in os.environ.items()
        if not (k.startswith("ANTHROPIC") or (k.startswith("CLAUDE") and k not in ("CLAUDE_BIN", "CLAUDE_CODE_OAUTH_TOKEN")))
    }

    def _dene(resume_id: str | None) -> dict:
        cmd = [
            claude_bin,
            "-p", soru,
            "--model", CLAUDE_MODEL,
            "--allowedTools", ALLOWED_TOOLS,
            "--output-format", "json",
        ]
        if resume_id:
            # Oturum sürüyor: sistem promptu ve önceki konuşma oturumda zaten var.
            cmd += ["--resume", resume_id]
        else:
            cmd += ["--append-system-prompt", _system_prompt()]

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
            return {"ok": False, "session_id": None,
                    "hata": "Sorgu zaman aşımına uğradı. Lütfen soruyu sadeleştirin."}
        except FileNotFoundError:
            return {"ok": False, "session_id": None,
                    "hata": "Claude Code sunucuda kurulu değil (PATH'te 'claude' yok)."}

        if sonuc.returncode != 0:
            # claude CLI hata detayını çoğu zaman stderr yerine stdout'a JSON
            # olarak yazar (ör. abonelik/limit/oturum hataları) — ikisine de bak.
            detay = (sonuc.stderr or "").strip()
            if not detay:
                ham = (sonuc.stdout or "").strip()
                try:
                    j = json.loads(ham)
                    detay = j.get("result") or j.get("error") or ham[:500]
                except (json.JSONDecodeError, AttributeError):
                    detay = ham[:500]
            import logging
            logging.getLogger(__name__).error(
                "[AI-ASISTAN] claude rc=%s resume=%s stderr=%r stdout=%r",
                sonuc.returncode, bool(resume_id),
                (sonuc.stderr or "")[:500], (sonuc.stdout or "")[:500],
            )
            return {"ok": False, "session_id": None,
                    "hata": f"Asistan hatası: {detay or 'bilinmeyen hata'}"}

        # --output-format json → {"result": "...", "session_id": "...", ...} bekleniyor
        try:
            data = json.loads(sonuc.stdout)
            cevap = data.get("result") or data.get("text") or ""
            session_id = data.get("session_id")
        except (json.JSONDecodeError, AttributeError):
            cevap = sonuc.stdout.strip()
            session_id = None

        if not cevap:
            return {"ok": False, "session_id": None, "hata": "Asistandan boş cevap geldi."}

        return {"ok": True, "cevap": cevap, "session_id": session_id}

    sonuc = _dene(resume_session_id)
    if not sonuc["ok"] and resume_session_id:
        # Oturum kayıp/bozuk olabilir → taze oturumla tek yeniden deneme.
        sonuc = _dene(None)
    return sonuc


def _ai_calistir(soru: str, resume_session_id: str | None = None) -> dict:
    """
    Seçili motora göre Claude Code veya Codex CLI'yi çalıştırır (aynı sözleşme).
    Motor panelden değiştirilebilir; ayar yoksa .env'deki AI_MOTOR geçerlidir.
    Codex tarafında da resume başarısız olursa taze oturumla bir kez denenir.
    """
    from ai_asistan.motor_ayar import aktif_motor

    if aktif_motor("asistan") != "codex":
        return _claude_calistir(soru, resume_session_id)

    sonuc = _codex_calistir(soru, _system_prompt(), QUERY_TIMEOUT_SN, resume_session_id)
    if not sonuc["ok"] and resume_session_id:
        sonuc = _codex_calistir(soru, _system_prompt(), QUERY_TIMEOUT_SN, None)
    return sonuc


def _arka_planda_cevapla(app, mesaj_id: int, sohbet_id: int, soru: str) -> None:
    """
    Thread gövdesi: Claude'u çalıştır, sonucu 'bekliyor' durumundaki asistan
    mesajına yaz. İstek worker'ı bloklanmaz; frontend /durum/<id> ile yoklar.
    """
    with app.app_context():
        try:
            sohbet = db.session.get(AiSohbet, sohbet_id)
            resume_id = sohbet.claude_session_id if sohbet else None

            sonuc = _ai_calistir(soru, resume_id)

            mesaj = db.session.get(AiMesaj, mesaj_id)
            if mesaj is None:                      # sohbet bu arada silinmiş
                return
            if sonuc["ok"]:
                mesaj.metin = sonuc["cevap"]
                mesaj.durum = "hazir"
                if sohbet is not None and sonuc.get("session_id"):
                    sohbet.claude_session_id = sonuc["session_id"]
            else:
                mesaj.metin = sonuc.get("hata") or "Bilinmeyen hata."
                mesaj.durum = "hata"
            db.session.commit()
        except Exception:
            app.logger.exception("[AI-ASISTAN] arka plan cevaplama hatası")
            try:
                db.session.rollback()
                mesaj = db.session.get(AiMesaj, mesaj_id)
                if mesaj is not None and mesaj.durum == "bekliyor":
                    mesaj.metin = "Beklenmeyen bir hata oluştu. Lütfen tekrar deneyin."
                    mesaj.durum = "hata"
                    db.session.commit()
            except Exception:
                db.session.rollback()
        finally:
            db.session.remove()


def _bayat_bekleyenleri_isaretle(uid: str) -> None:
    """
    Zaman aşımını çoktan geçmiş 'bekliyor' mesajlarını 'hata'ya düşür.
    Cevap thread'i worker restart'ında (deploy, OOM) ölürse mesaj sonsuza dek
    bekliyor'da kalır ve tek-bekleyen kilidi kullanıcıyı kilitlerdi.
    """
    esik = datetime.utcnow() - timedelta(seconds=QUERY_TIMEOUT_SN + 60)
    bayatlar = (
        AiMesaj.query
        .join(AiSohbet, AiMesaj.sohbet_id == AiSohbet.id)
        .filter(AiSohbet.kullanici == uid,
                AiMesaj.durum == "bekliyor",
                AiMesaj.created_at < esik)
        .all()
    )
    if not bayatlar:
        return
    for m in bayatlar:
        m.metin = "Cevap tamamlanamadı (sunucu yeniden başlamış olabilir). Lütfen soruyu tekrar sorun."
        m.durum = "hata"
    db.session.commit()


def _utc_iso(dt) -> str | None:
    """Naive-UTC timestamp'ı JS'in yerel saate çevirebilmesi için 'Z' ekiyle döndür."""
    return (dt.isoformat() + "Z") if dt else None


@ai_asistan_bp.route("/", methods=["GET"])
@login_required
def sayfa():
    """Sohbet kutusu sayfası."""
    return render_template("ai_asistan.html")


@ai_asistan_bp.route("/motor", methods=["GET", "POST"])
@login_required
def motor():
    """
    AI motoru (claude|codex) oku/değiştir. Her iki ekran da (asistan, qna) bu
    endpoint'i kullanır. Değiştirme YALNIZCA yöneticiye açık — motor seçimi
    maliyet/gizlilik etkisi olan bir sistem ayarı.
    """
    from ai_asistan.motor_ayar import motor_ayarla, motorlari_getir

    if request.method == "GET":
        return jsonify({"ok": True, "motorlar": motorlari_getir(),
                        "duzenleyebilir": _yonetici_mi()})

    if not _yonetici_mi():
        return jsonify({"ok": False, "hata": "Bu ayarı yalnızca yönetici değiştirebilir."}), 403

    # Basit CSRF kalkanı (qna_routes.py:40 ile aynı desen): siteler arası form
    # POST'u bu özel başlığı gönderemez, fetch gönderir.
    if request.headers.get("X-Requested-With") != "fetch":
        return jsonify({"ok": False, "hata": "Geçersiz istek."}), 400

    payload = request.get_json(silent=True) or {}
    alan = (payload.get("alan") or "").strip()
    secim = (payload.get("motor") or "").strip().lower()
    try:
        motor_ayarla(alan, secim)
    except ValueError as e:
        return jsonify({"ok": False, "hata": str(e)}), 400
    except Exception:
        db.session.rollback()
        current_app.logger.exception("[AI-MOTOR] ayar yazılamadı")
        return jsonify({"ok": False, "hata": "Ayar kaydedilemedi."}), 500

    current_app.logger.info("[AI-MOTOR] %s → %s (kullanıcı=%s)", alan, secim, _kullanici_id())
    return jsonify({"ok": True, "motorlar": motorlari_getir()})


@ai_asistan_bp.route("/sor", methods=["POST"])
@login_required
def sor():
    """
    Soruyu al, doğrula, DB'ye yaz, Claude'u ARKA PLANDA başlat ve anında dön.
    Dönen: {ok, sohbet_id, mesaj_id, baslik} — frontend /durum/<mesaj_id> yoklar.
    """
    payload = request.get_json(silent=True) or {}
    soru = (payload.get("soru") or "").strip()
    sohbet_id = payload.get("sohbet_id")

    # Girdi doğrulama (sistem sınırında)
    if not soru:
        return jsonify({"ok": False, "hata": "Soru boş olamaz."}), 400
    if len(soru) > MAX_SORU_UZUNLUK:
        return jsonify({"ok": False, "hata": "Soru çok uzun."}), 400

    uid = _kullanici_id()
    _bayat_bekleyenleri_isaretle(uid)

    # Aynı anda kullanıcı başına tek bekleyen soru (Claude süreçleri yığılmasın).
    bekleyen = (
        db.session.query(AiMesaj.id)
        .join(AiSohbet, AiMesaj.sohbet_id == AiSohbet.id)
        .filter(AiSohbet.kullanici == uid, AiMesaj.durum == "bekliyor")
        .first()
    )
    if bekleyen:
        return jsonify({"ok": False, "hata": "Önceki sorunun cevabı hazırlanıyor; lütfen bekleyin."}), 429

    if sohbet_id:
        sohbet = _sohbet_getir(int(sohbet_id))
    else:
        sohbet = AiSohbet(kullanici=uid, baslik=soru[:BASLIK_UZUNLUK])
        db.session.add(sohbet)
        db.session.flush()

    sohbet.updated_at = datetime.utcnow()
    db.session.add(AiMesaj(sohbet_id=sohbet.id, rol="kullanici", metin=soru, durum="hazir"))
    cevap_mesaj = AiMesaj(sohbet_id=sohbet.id, rol="asistan", metin="", durum="bekliyor")
    db.session.add(cevap_mesaj)
    db.session.commit()

    t = threading.Thread(
        target=_arka_planda_cevapla,
        args=(current_app._get_current_object(), cevap_mesaj.id, sohbet.id, soru),
        daemon=True,
    )
    t.start()

    return jsonify({
        "ok": True,
        "sohbet_id": sohbet.id,
        "mesaj_id": cevap_mesaj.id,
        "baslik": sohbet.baslik,
    })


@ai_asistan_bp.route("/durum/<int:mesaj_id>", methods=["GET"])
@login_required
def durum(mesaj_id: int):
    """Bekleyen cevabın durumunu döndür (frontend 2 sn'de bir yoklar)."""
    mesaj = db.session.get(AiMesaj, mesaj_id)
    if mesaj is None:
        abort(404)
    _sohbet_getir(mesaj.sohbet_id)   # sahiplik kontrolü
    if mesaj.durum == "bekliyor":
        _bayat_bekleyenleri_isaretle(_kullanici_id())
        db.session.refresh(mesaj)
    return jsonify({"ok": True, "durum": mesaj.durum, "metin": mesaj.metin})


@ai_asistan_bp.route("/sohbetler", methods=["GET"])
@login_required
def sohbetler():
    """Kullanıcının sohbet listesi (en yeni üstte)."""
    uid = _kullanici_id()
    _eski_json_ice_al(uid)
    kayitlar = (
        AiSohbet.query.filter_by(kullanici=uid)
        .order_by(AiSohbet.updated_at.desc())
        .limit(MAX_SOHBET_LISTE)
        .all()
    )
    return jsonify({"ok": True, "sohbetler": [
        {"id": s.id, "baslik": s.baslik, "updated_at": _utc_iso(s.updated_at)}
        for s in kayitlar
    ]})


@ai_asistan_bp.route("/sohbet/<int:sohbet_id>", methods=["GET"])
@login_required
def sohbet_detay(sohbet_id: int):
    """Bir sohbetin mesajlarını döndür (tıkla-devam-et)."""
    sohbet = _sohbet_getir(sohbet_id)
    mesajlar = (
        AiMesaj.query.filter_by(sohbet_id=sohbet.id)
        .order_by(AiMesaj.id.asc())
        .all()
    )
    return jsonify({"ok": True, "baslik": sohbet.baslik, "mesajlar": [
        {"id": m.id, "rol": m.rol, "metin": m.metin, "durum": m.durum}
        for m in mesajlar
    ]})


@ai_asistan_bp.route("/sohbet/<int:sohbet_id>/sil", methods=["POST"])
@login_required
def sohbet_sil(sohbet_id: int):
    """Sohbeti ve mesajlarını sil."""
    sohbet = _sohbet_getir(sohbet_id)
    AiMesaj.query.filter_by(sohbet_id=sohbet.id).delete()
    db.session.delete(sohbet)
    db.session.commit()
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
