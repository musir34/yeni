"""
Codex için SQL köprüsü — MCP olmadan salt-okunur veritabanı erişimi.

NEDEN: Codex CLI 0.144.6 headless (`codex exec`) modunda MCP araç çağrılarını
"user cancelled MCP tool call" ile reddediyor (approval_policy varyantları,
auto_approve/trusted/always_allow/enabled_tools, --disable tool_search, uzun
timeout ve apparmor/sandbox düzeltmesi denendi; hiçbiri geçmedi). Claude tarafı
MCP ile çalışmaya devam eder; Codex'te aynı yetenek burada MCP'siz sağlanır.

NASIL: Codex cevabında ```sql ... ``` bloğu yazar → blueprint bu bloğu buraya
verir → doğrulanıp ai_readonly rolüyle çalıştırılır → sonuç bir sonraki tura
beslenir. Böylece Claude'un MCP döngüsünün eşdeğeri (keşif + çok adımlı sorgu)
elde edilir.

GÜVENLİK KATMANLARI:
1. ai_readonly rolü yazamaz — fiziksel sınır (MCP'li kurulumla aynı temel).
2. Yalnızca TEK bir SELECT/WITH ifadesi; DML/DDL anahtar kelimeleri reddedilir.
3. statement_timeout + satır ve karakter sınırı.
4. SQL Python'da çalışır; Codex'e shell veya ağ yetkisi VERİLMEZ.
"""
import logging
import os
import re

from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

SORGU_TIMEOUT_MS = 30000       # DB tarafında statement_timeout
AZAMI_SATIR = 200              # modele beslenecek azami satır
AZAMI_KARAKTER = 12000         # sonuç metninin azami boyutu (prompt şişmesin)

# Tek ifade + salt-okunur güvencesi: ai_readonly zaten yazamaz, bu ikinci katman.
YASAKLI = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|"
    r"vacuum|reindex|refresh|call|do|set|reset|lock)\b",
    re.IGNORECASE,
)

_engine = None


def _motor():
    """ai_readonly bağlantı havuzu (tembel kurulum)."""
    global _engine
    if _engine is None:
        url = os.getenv("AI_DB_URL")
        if not url:
            raise RuntimeError("AI_DB_URL tanımlı değil (.env).")
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"options": f"-c statement_timeout={SORGU_TIMEOUT_MS}"},
        )
    return _engine


def sql_dogrula(sql: str) -> str:
    """
    Salt-okunur tek ifade mi? Değilse ValueError.
    Dönen: temizlenmiş SQL (sondaki ';' atılmış).
    """
    temiz = (sql or "").strip().rstrip(";").strip()
    if not temiz:
        raise ValueError("Boş sorgu.")
    if ";" in temiz:
        raise ValueError("Tek seferde yalnızca BİR sorgu çalıştırılabilir.")
    if not re.match(r"^(select|with)\b", temiz, re.IGNORECASE):
        raise ValueError("Yalnızca SELECT (veya WITH ... SELECT) sorgularına izin var.")
    yasak = YASAKLI.search(temiz)
    if yasak:
        raise ValueError(f"Yasaklı anahtar kelime: {yasak.group(0)}")
    return temiz


def sql_calistir(sql: str) -> str:
    """
    Doğrulanmış SELECT'i çalıştır, sonucu modele verilecek metne çevir.
    Hata metni de modele döner — Codex sorguyu düzeltip tekrar deneyebilsin.
    """
    try:
        temiz = sql_dogrula(sql)
    except ValueError as e:
        return f"SORGU REDDEDİLDİ: {e}"

    try:
        with _motor().connect() as baglanti:
            sonuc = baglanti.execute(text(temiz))
            sutunlar = list(sonuc.keys())
            satirlar = sonuc.fetchmany(AZAMI_SATIR + 1)
    except Exception as e:
        logger.warning("[SQL-KOPRU] sorgu hatası: %s", e)
        return f"SORGU HATASI: {str(e)[:500]}"

    return _tabloya_cevir(sutunlar, satirlar)


def _tabloya_cevir(sutunlar: list, satirlar: list) -> str:
    """Sonucu kompakt boru-ayraçlı tabloya çevir (modelin okuması kolay)."""
    if not satirlar:
        return "SONUÇ: 0 satır."

    kirpildi = len(satirlar) > AZAMI_SATIR
    satirlar = satirlar[:AZAMI_SATIR]

    parcalar = [" | ".join(str(s) for s in sutunlar)]
    parcalar.append("-" * min(len(parcalar[0]), 80))
    for satir in satirlar:
        parcalar.append(" | ".join("" if d is None else str(d) for d in satir))

    metin = "\n".join(parcalar)
    if len(metin) > AZAMI_KARAKTER:
        metin = metin[:AZAMI_KARAKTER] + "\n… (çıktı kısaltıldı)"
    if kirpildi:
        metin += f"\n… (yalnızca ilk {AZAMI_SATIR} satır gösterildi; "
        metin += "daha dar bir sorgu veya toplama (GROUP BY) kullan)"
    return metin


def sema_ozeti() -> str:
    """
    public şemasındaki tablo ve sütunların kompakt özeti.
    Codex'e sistem promptuyla verilir — MCP'li kurulumda Claude'un keşifle
    öğrendiği bilgiyi Codex peşinen alsın diye.
    """
    sorgu = """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
    """
    try:
        with _motor().connect() as baglanti:
            satirlar = baglanti.execute(text(sorgu)).fetchall()
    except Exception as e:
        logger.warning("[SQL-KOPRU] şema özeti alınamadı: %s", e)
        return "(şema özeti alınamadı; tabloları information_schema üzerinden keşfet)"

    tablolar: dict[str, list[str]] = {}
    for tablo, sutun, tip in satirlar:
        tablolar.setdefault(tablo, []).append(f"{sutun} {_kisa_tip(tip)}")

    return "\n".join(f"{ad}({', '.join(sutunlar)})" for ad, sutunlar in tablolar.items())


def _kisa_tip(tip: str) -> str:
    """Şema özetini şişirmemek için tip adlarını kısalt."""
    kisaltma = {
        "character varying": "str", "text": "str", "integer": "int",
        "bigint": "int", "smallint": "int", "boolean": "bool",
        "timestamp without time zone": "ts", "timestamp with time zone": "tstz",
        "double precision": "float", "numeric": "num", "date": "date",
        "jsonb": "json", "json": "json",
    }
    return kisaltma.get(tip, tip)
