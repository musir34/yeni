"""Serbest metin adresten il / ilçe çıkarma (MNG cityName/districtName için).

Değişim ve manuel sipariş formlarında adres tek metin kutusu; MNG ise il adını zorunlu
ister (cityCode=0 iken cityName). Form il/ilçe vermediyse adres metninde 81 il adı
aranır (sondan başa: "... Kadıköy / İstanbul"), ilçe olarak il'den hemen önceki
sözcük(ler) alınır. Bulunamazsa boş döner; kayıt 'bekliyor'da kalır ve gönderi
sayfasından il/ilçe düzeltilip yeniden denenir.
"""
from __future__ import annotations

import re
import unicodedata

from .govde import Alici

ILLER = (
    "ADANA", "ADIYAMAN", "AFYONKARAHİSAR", "AĞRI", "AMASYA", "ANKARA", "ANTALYA", "ARTVİN", "AYDIN",
    "BALIKESİR", "BİLECİK", "BİNGÖL", "BİTLİS", "BOLU", "BURDUR", "BURSA", "ÇANAKKALE", "ÇANKIRI",
    "ÇORUM", "DENİZLİ", "DİYARBAKIR", "EDİRNE", "ELAZIĞ", "ERZİNCAN", "ERZURUM", "ESKİŞEHİR",
    "GAZİANTEP", "GİRESUN", "GÜMÜŞHANE", "HAKKARİ", "HATAY", "ISPARTA", "MERSİN", "İSTANBUL", "İZMİR",
    "KARS", "KASTAMONU", "KAYSERİ", "KIRKLARELİ", "KIRŞEHİR", "KOCAELİ", "KONYA", "KÜTAHYA", "MALATYA",
    "MANİSA", "KAHRAMANMARAŞ", "MARDİN", "MUĞLA", "MUŞ", "NEVŞEHİR", "NİĞDE", "ORDU", "RİZE", "SAKARYA",
    "SAMSUN", "SİİRT", "SİNOP", "SİVAS", "TEKİRDAĞ", "TOKAT", "TRABZON", "TUNCELİ", "ŞANLIURFA", "UŞAK",
    "VAN", "YOZGAT", "ZONGULDAK", "AKSARAY", "BAYBURT", "KARAMAN", "KIRIKKALE", "BARTIN", "ARDAHAN",
    "IĞDIR", "YALOVA", "KARABÜK", "KİLİS", "OSMANİYE", "DÜZCE", "BATMAN", "ŞIRNAK",
)
# Yazımda sık görülen eş adlar → kanonik il
ES_ADLAR = {"AFYON": "AFYONKARAHİSAR", "MARAS": "KAHRAMANMARAŞ", "URFA": "ŞANLIURFA", "ICEL": "MERSİN", "ANTEP": "GAZİANTEP"}
# Plaka kodu → il (MNG il kodu = plaka; posta kodunun ilk 2 hanesi)
PLAKA = {
    "01": "ADANA", "02": "ADIYAMAN", "03": "AFYONKARAHİSAR", "04": "AĞRI", "05": "AMASYA", "06": "ANKARA",
    "07": "ANTALYA", "08": "ARTVİN", "09": "AYDIN", "10": "BALIKESİR", "11": "BİLECİK", "12": "BİNGÖL",
    "13": "BİTLİS", "14": "BOLU", "15": "BURDUR", "16": "BURSA", "17": "ÇANAKKALE", "18": "ÇANKIRI",
    "19": "ÇORUM", "20": "DENİZLİ", "21": "DİYARBAKIR", "22": "EDİRNE", "23": "ELAZIĞ", "24": "ERZİNCAN",
    "25": "ERZURUM", "26": "ESKİŞEHİR", "27": "GAZİANTEP", "28": "GİRESUN", "29": "GÜMÜŞHANE", "30": "HAKKARİ",
    "31": "HATAY", "32": "ISPARTA", "33": "MERSİN", "34": "İSTANBUL", "35": "İZMİR", "36": "KARS",
    "37": "KASTAMONU", "38": "KAYSERİ", "39": "KIRKLARELİ", "40": "KIRŞEHİR", "41": "KOCAELİ", "42": "KONYA",
    "43": "KÜTAHYA", "44": "MALATYA", "45": "MANİSA", "46": "KAHRAMANMARAŞ", "47": "MARDİN", "48": "MUĞLA",
    "49": "MUŞ", "50": "NEVŞEHİR", "51": "NİĞDE", "52": "ORDU", "53": "RİZE", "54": "SAKARYA", "55": "SAMSUN",
    "56": "SİİRT", "57": "SİNOP", "58": "SİVAS", "59": "TEKİRDAĞ", "60": "TOKAT", "61": "TRABZON", "62": "TUNCELİ",
    "63": "ŞANLIURFA", "64": "UŞAK", "65": "VAN", "66": "YOZGAT", "67": "ZONGULDAK", "68": "AKSARAY", "69": "BAYBURT",
    "70": "KARAMAN", "71": "KIRIKKALE", "72": "BATMAN", "73": "ŞIRNAK", "74": "BARTIN", "75": "ARDAHAN", "76": "IĞDIR",
    "77": "YALOVA", "78": "KARABÜK", "79": "KİLİS", "80": "OSMANİYE", "81": "DÜZCE",
}


def tr_upper(metin: str) -> str:
    return (metin or "").replace("i", "İ").replace("ı", "I").upper()


def sadelestir(metin: str) -> str:
    """Büyük harf + aksan/Türkçe karakter düzleştirme (eşleştirme anahtarı)."""
    ust = tr_upper(metin)
    ust = ust.replace("İ", "I").replace("Ş", "S").replace("Ğ", "G").replace("Ü", "U").replace("Ö", "O").replace("Ç", "C")
    return "".join(c for c in unicodedata.normalize("NFKD", ust) if not unicodedata.combining(c))


_IL_ANAHTAR = {sadelestir(il): il for il in ILLER}
_IL_ANAHTAR.update({sadelestir(k): v for k, v in ES_ADLAR.items()})
_AYRAC = re.compile(r"[\s/,\-\.\(\)]+")


def il_bul(metin: str) -> str:
    """Metindeki (sondan) ilk il adını kanonik yazımla döndürür; yoksa ''."""
    sozcukler = [s for s in _AYRAC.split(sadelestir(metin)) if s]
    for s in reversed(sozcukler):
        if s in _IL_ANAHTAR:
            return _IL_ANAHTAR[s]
    return ""


def il_ilce_ayikla(adres: str) -> tuple[str, str]:
    """('İSTANBUL', 'KADIKÖY') — ilçe: il'den hemen önceki sözcük (posta kodu / 'MAH' değilse)."""
    il = il_bul(adres)
    if not il:
        return "", ""
    ham = [s for s in _AYRAC.split(adres or "") if s]
    anahtarlar = [sadelestir(s) for s in ham]
    il_anahtar = sadelestir(il)
    konum = -1
    for i in range(len(anahtarlar) - 1, -1, -1):
        if _IL_ANAHTAR.get(anahtarlar[i]) == il:
            konum = i
            break
    ilce = ""
    if konum > 0:
        aday = ham[konum - 1]
        aday_anahtar = anahtarlar[konum - 1]
        if not aday_anahtar.isdigit() and aday_anahtar not in {"MAH", "MAHALLESI", "SOK", "CAD", "NO", "KAT", "D", "DAIRE", "APT"}:
            ilce = tr_upper(aday)
    return il, ilce


def plaka_il(posta_kodu: str) -> str:
    """Posta kodunun ilk iki hanesi = plaka = MNG il kodu → kanonik il adı ('34212' → İSTANBUL)."""
    rakamlar = re.sub(r"\D", "", str(posta_kodu or ""))
    if len(rakamlar) != 5:
        return ""
    return PLAKA.get(rakamlar[:2], "")


def alici_kur(ad_soyad: str, adres: str, telefon: str, il: str = "", ilce: str = "", email: str = "",
              posta_kodu: str = "") -> Alici:
    """İl: form/province → ilçe metninde il adı → posta kodu plakası → adres metni.
    (Shopify TR: province sık boş, city serbest metin; 'İzmir', 'İZMİT/KOCAELİ', 'Bir seçenek belirleyin…')"""
    il = tr_upper((il or "").strip())
    ilce = tr_upper((ilce or "").strip())
    if il and not il_bul(il):
        il = ""                                   # 'Bir seçenek belirleyin…' gibi çöp
    if not il and ilce:
        il_ilceden = il_bul(ilce)
        if il_ilceden:
            il = il_ilceden
            if sadelestir(ilce) == sadelestir(il):
                ilce = ""                         # city='İstanbul' → ilçe bilinmiyor
    if not il:
        il = plaka_il(posta_kodu)
    if not il:
        il_adres, ilce_adres = il_ilce_ayikla(adres)
        il = il_adres
        ilce = ilce or ilce_adres
    il_kanonik = _IL_ANAHTAR.get(sadelestir(il), il) if il else ""
    if ilce and il_kanonik and sadelestir(ilce) == sadelestir(il_kanonik):
        ilce = ""                                 # city='İstanbul', province='Istanbul' → ilçe yok
    return Alici(ad_soyad=(ad_soyad or "").strip(), adres=(adres or "").strip(), telefon=(telefon or "").strip(),
                 il=il_kanonik, ilce=ilce, email=(email or "").strip())
