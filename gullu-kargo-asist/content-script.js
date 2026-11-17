// Bildirim Kutusu
function showNotification(text, color) {
  color = color || "#28a745";
  var div = document.createElement("div");
  div.innerText = text;
  div.style.position = "fixed";
  div.style.bottom = "20px";
  div.style.right = "20px";
  div.style.padding = "10px 20px";
  div.style.backgroundColor = color;
  div.style.color = "white";
  div.style.fontWeight = "bold";
  div.style.borderRadius = "8px";
  div.style.zIndex = "99999";
  div.style.boxShadow = "0 0 10px rgba(0,0,0,0.3)";
  div.style.fontSize = "14px";
  document.body.appendChild(div);
  setTimeout(function() { div.remove(); }, 4000);
}

// GULLU TARAFI - Otomatik Gonderim kodunu DOM'dan dinle
if (location.hostname.includes("gullupanel.com")) {
  showNotification("[Gullu Asist] Aktif - kod bekleniyor...", "#6c757d");
  var sonGonderilenKod = "";
  var logSayaci = 0;

  setInterval(function() {
    var messageBox = document.getElementById("autoShipBarcode");

    logSayaci++;
    if (logSayaci <= 60 && logSayaci % 10 === 0) {
      if (!messageBox) {
        showNotification("[Gullu Asist] autoShipBarcode bulunamiyor!", "#ffc107");
        console.log("[Gullu Asist] autoShipBarcode elementi bulunamadi.");
      } else {
        var icerik = messageBox.innerText.trim();
        if (!icerik) {
          showNotification("[Gullu Asist] Element var, kod bekleniyor...", "#17a2b8");
        } else {
          console.log("[Gullu Asist] Element icerigi:", icerik);
        }
      }
    }

    if (messageBox) {
      var icerikTxt = messageBox.innerText.trim();
      var eslesme = icerikTxt.match(/\d{10,20}/);
      var kod = eslesme ? eslesme[0] : null;

      if (kod && kod !== sonGonderilenKod) {
        sonGonderilenKod = kod;

        // Urun adedi: once kodun uzerindeki data-urun-adet (uretim ekrani bunu verir),
        // yoksa aktif siparisteki product-card sayisi (siparis hazirla ekrani)
        var adetAttr = parseInt(messageBox.getAttribute("data-urun-adet") || "", 10);
        var urunAdet = adetAttr > 0 ? adetAttr : 0;
        if (!urunAdet) {
          var urunKartlari = document.querySelectorAll(".order-container .product-card");
          urunAdet = (urunKartlari && urunKartlari.length) ? urunKartlari.length : 1;
        }

        chrome.runtime.sendMessage({ kargoKodu: kod, urunAdet: urunAdet });
        showNotification("[Gullu Asist] Kod alindi: " + kod + " (" + urunAdet + " urun)", "#28a745");
        console.log("[Gullu Asist] Gonderilen Kod:", kod, "Urun Adet:", urunAdet);
      }
    }
  }, 1000);
}

// DHL TARAFI - gelen kodu input'a yaz ve islemi tetikle
// SADECE Gonderi Hazirlik sayfasinda calissin
if (location.hostname.includes("onlinesube.dhlecommerce.com.tr") &&
    location.pathname.indexOf("/Gonder/GonderiHazirlik") !== -1) {
  console.log("[Gullu Asist] DHL Gonderi Hazirlik sayfasi dinlemeye hazir");
  showNotification("[Gullu Asist] DHL dinlemede...", "#6c757d");

  // =====================================================
  // ZPL Yakalayici - inject.js (MAIN world) postMessage ile gonderir
  // Yakalanan ZPL'i background'a ilet, gunluk PDF'e eklensin
  // =====================================================
  var sonGonderilenZpl = "";
  var sonGonderimZamani = 0;
  window.addEventListener("message", function(event) {
    if (event.source !== window) return;
    var d = event.data;
    if (!d || !d.__gulluZpl || typeof d.zpl !== "string") return;
    // Ayni ZPL'i kisa surede tekrar gonderme (QZ retry)
    var simdi = Date.now();
    if (d.zpl === sonGonderilenZpl && (simdi - sonGonderimZamani) < 5000) return;
    sonGonderilenZpl = d.zpl;
    sonGonderimZamani = simdi;
    chrome.runtime.sendMessage({ zplCapture: d.zpl }, function() {
      if (chrome.runtime.lastError) {
        console.warn("[Gullu Asist] ZPL background'a iletilemedi:", chrome.runtime.lastError.message);
      }
    });
    showNotification("[Gullu Asist] Etiket yakalandi (PDF'e ekleniyor)", "#17a2b8");
  });

  // =====================================================
  // 0) Sayfa ilk acildiginda otomatik doldurma
  // - Kargo Sorumlusu Ad/Soyad: ABDURRAHMAN / KULI
  // - Gonderen Birim "Sabitle" toggle aktif
  // - Hizli E-ticaret checkbox aktif
  // - Platform: Trendyol
  // - Takip Bilgileri "Sabitle" toggle aktif
  // =====================================================
  var SABIT_AD = "ABDURRAHMAN";
  var SABIT_SOYAD = "KULI";
  var PARCA_KAYDET_BEKLEME_MS = 5000;   // Parcayi Kaydet butonunun acilmasi icin azami bekleme
  var ilkDoldurmaYapildi = false;

  function ilkDoldurmaYap() {
    if (ilkDoldurmaYapildi) return;

    // Gerekli elementler yuklendi mi?
    var adInput = document.querySelector("#txtYetkiliAd");
    var soyadInput = document.querySelector("#txtYetkiliSoyad");
    var hizliCb = document.querySelector("#chkHizliEticaret");
    var platformSelect = document.querySelector("#select-platform");
    var birimSabitChk = document.querySelector("#checkbox-gonderi-birim-departmani");
    var takipSabitChk = document.querySelector("#checkbox-kargo-takip-bilgileri");

    // Hepsi yuklenmediyse bekle
    if (!adInput || !soyadInput || !hizliCb || !platformSelect || !birimSabitChk || !takipSabitChk) {
      return;
    }

    // Platform select'te Trendyol var mi kontrol et (platformlar AJAX ile dolduruluyor)
    var trendyolOption = platformSelect.querySelector('option[value="TRND"]');
    if (!trendyolOption) {
      return;
    }

    ilkDoldurmaYapildi = true;
    console.log("[Gullu Asist] Ilk doldurma baslatiliyor...");

    // 1) Kargo Sorumlusu Ad/Soyad
    if (!adInput.value.trim()) {
      adInput.value = SABIT_AD;
      adInput.dispatchEvent(new Event("input", { bubbles: true }));
      adInput.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (!soyadInput.value.trim()) {
      soyadInput.value = SABIT_SOYAD;
      soyadInput.dispatchEvent(new Event("input", { bubbles: true }));
      soyadInput.dispatchEvent(new Event("change", { bubbles: true }));
    }
    console.log("[Gullu Asist] Kargo sorumlusu dolduruldu:", SABIT_AD, SABIT_SOYAD);

    // 2) Gonderen Birim "Sabitle" toggle - Switchery kullaniyor
    setTimeout(function() {
      if (!birimSabitChk.checked) {
        // Switchery'nin render ettigi DOM elementi tiklat
        var switcheryEl = birimSabitChk.nextElementSibling;
        if (switcheryEl && switcheryEl.classList.contains("switchery")) {
          switcheryEl.click();
        } else {
          birimSabitChk.checked = true;
          birimSabitChk.dispatchEvent(new Event("change", { bubbles: true }));
        }
        console.log("[Gullu Asist] Gonderen Birim sabitle aktif edildi");
      }
    }, 200);

    // 3) Hizli E-ticaret checkbox
    setTimeout(function() {
      if (!hizliCb.checked) {
        hizliCb.checked = true;
        hizliCb.dispatchEvent(new Event("change", { bubbles: true }));
        console.log("[Gullu Asist] Hizli E-ticaret aktif edildi");
      }
    }, 400);

    // 4) Platform: Trendyol
    setTimeout(function() {
      if (platformSelect.value !== "TRND") {
        if (typeof jQuery !== "undefined") {
          jQuery(platformSelect).val("TRND").trigger("change");
        } else {
          platformSelect.value = "TRND";
          platformSelect.dispatchEvent(new Event("change", { bubbles: true }));
        }
        console.log("[Gullu Asist] Platform Trendyol secildi");
      }
    }, 600);

    // 5) Takip Bilgileri "Sabitle" toggle
    setTimeout(function() {
      if (!takipSabitChk.checked) {
        var switcheryEl = takipSabitChk.nextElementSibling;
        if (switcheryEl && switcheryEl.classList.contains("switchery")) {
          switcheryEl.click();
        } else {
          takipSabitChk.checked = true;
          takipSabitChk.dispatchEvent(new Event("change", { bubbles: true }));
        }
        console.log("[Gullu Asist] Takip Bilgileri sabitle aktif edildi");
      }
      showNotification("[Gullu Asist] Sayfa hazirlandi", "#28a745");
    }, 800);
  }

  // Sayfa acildiktan 3 saniye sonra ilk doldurmaya basla
  setTimeout(function() {
    var ilkDoldurmaInterval = setInterval(function() {
      ilkDoldurmaYap();
      if (ilkDoldurmaYapildi) {
        clearInterval(ilkDoldurmaInterval);
      }
    }, 500);

    // 30 saniye sonra hala yapilmadiysa vazgec
    setTimeout(function() {
      if (!ilkDoldurmaYapildi) {
        clearInterval(ilkDoldurmaInterval);
        console.warn("[Gullu Asist] Ilk doldurma zamanasimi");
      }
    }, 30000);
  }, 3000);

  // =====================================================
  // 1) "Her Kayittan Sonra Yazdirilsin" her zaman aktif tut
  // =====================================================
  function yazdirmaCheckboxKoru() {
    var cb = document.querySelector("#checkbox-her-gonderi-sonrasinda-yazdir");
    if (cb && !cb.checked) {
      cb.checked = true;
      // Label'a da active class ekle (gorunum icin)
      var label = cb.closest(".print-toggle-wrapper");
      if (label) {
        var labelEl = label.querySelector("label");
        if (labelEl) labelEl.classList.add("active");
      }
      console.log("[Gullu Asist] Yazdirma checkbox otomatik aktif edildi");
    }
  }

  // Sayfa yuklendiginde kontrol et
  yazdirmaCheckboxKoru();

  // DOM degisikliklerini izle (SayfaTemizlik/GetKullaniciTercihleri sonrasi resetlenirse yakala)
  var yazdirmaObserver = new MutationObserver(function() {
    yazdirmaCheckboxKoru();
  });

  // Checkbox'in parent'ini izle
  var yazdirmaWrapper = document.querySelector("#checkbox-her-gonderi-sonrasinda-yazdir");
  if (yazdirmaWrapper) {
    yazdirmaObserver.observe(yazdirmaWrapper.closest(".print-toggle-wrapper") || yazdirmaWrapper.parentElement, {
      attributes: true,
      subtree: true,
      attributeFilter: ["checked"]
    });
  }

  // Yedek: her 2 saniyede bir kontrol (MutationObserver checked attribute'u her zaman yakalamiyor)
  setInterval(yazdirmaCheckboxKoru, 2000);

  // =====================================================
  // 2) Kargo kodu mesaj dinleyici
  // =====================================================
  // =====================================================
  // Urun adedine gore DHL'de dogru paketi sec
  // 1 -> Tekli, 2 -> Ikili, 3 -> Uclu, 4 -> Dortlu, 5 -> Besli
  // 6 -> Altili, 7 -> Yedili, 8 -> Sekizli, 9 -> Dokuzlu, 10 -> Onlu
  // =====================================================

  // Turkce karakterleri normalize et (buyuk harfe cevir ve diacritik'leri temizle)
  function normalizeText(s) {
    if (!s) return "";
    return s
      .replace(/İ/g, "I").replace(/ı/g, "I")
      .replace(/Ş/g, "S").replace(/ş/g, "S")
      .replace(/Ğ/g, "G").replace(/ğ/g, "G")
      .replace(/Ü/g, "U").replace(/ü/g, "U")
      .replace(/Ö/g, "O").replace(/ö/g, "O")
      .replace(/Ç/g, "C").replace(/ç/g, "C")
      .toUpperCase();
  }

  var ADET_ISIM_MAP = {
    1: "TEKLI",
    2: "IKILI",
    3: "UCLU",
    4: "DORTLU",
    5: "BESLI",
    6: "ALTILI",
    7: "YEDILI",
    8: "SEKIZLI",
    9: "DOKUZLU",
    10: "ONLU"
  };

  function urunPaketiSec(adet, onComplete) {
    var select = document.querySelector("#select-musteri-urun");
    if (!select) {
      console.warn("[Gullu Asist] select-musteri-urun bulunamadi");
      if (onComplete) onComplete(false);
      return;
    }

    // 10'dan fazlaysa en buyuk paketi sec (Onlu)
    if (adet > 10) adet = 10;
    if (adet < 1) adet = 1;

    var aramaIsmi = ADET_ISIM_MAP[adet];
    if (!aramaIsmi) {
      console.warn("[Gullu Asist] Adet icin isim bulunamadi:", adet);
      if (onComplete) onComplete(false);
      return;
    }

    // Select option'lari arasinda dogru urunu bul
    var options = select.querySelectorAll("option");
    var hedefValue = null;

    for (var i = 0; i < options.length; i++) {
      var normalized = normalizeText(options[i].textContent.trim());
      // "(P)" onekini temizle
      var cleaned = normalized.replace(/\(P\)\s*/, "").trim();

      // Tam eslesme veya kelime olarak icerme
      if (cleaned === aramaIsmi || new RegExp("\\b" + aramaIsmi + "\\b").test(cleaned)) {
        hedefValue = options[i].value;
        break;
      }
    }

    if (hedefValue && select.value !== hedefValue) {
      // jQuery select2 varsa onunla tetikle, yoksa native
      if (typeof jQuery !== "undefined" && jQuery.fn.select2) {
        jQuery(select).val(hedefValue).trigger("change");
      } else {
        select.value = hedefValue;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
      console.log("[Gullu Asist] Urun secildi: " + aramaIsmi + " (adet=" + adet + ")");
      showNotification("[Gullu Asist] Paket: " + aramaIsmi + " (" + adet + " urun)", "#17a2b8");

      // Icerik doldur ve kaydet zincirini baslat
      setTimeout(function() {
        icerikDoldurVeKaydet(adet, onComplete);
      }, 300);
    } else if (hedefValue && select.value === hedefValue) {
      // Zaten secili - direkt icerik doldurmaya gec
      setTimeout(function() {
        icerikDoldurVeKaydet(adet, onComplete);
      }, 100);
    } else {
      console.warn("[Gullu Asist] Adet " + adet + " icin uygun urun bulunamadi");
      showNotification("[UYARI] " + adet + " urun icin paket bulunamadi!", "#ffc107");
      if (onComplete) onComplete(false);
    }
  }

  // =====================================================
  // DHL 2026-11 sayfa guncellemesi: Icerik Kategori/Icerik select'leri ve
  // "Iceriği Ekle" butonu kalkti; yerine serbest metin "Kargo Icerigi"
  // (#input-kargo-icerigi) geldi. Parca Adet (#input-paket-adet) artik KOLI
  // sayisidir -> her zaman 1 (urun adedi paket seciminde: TEKLI/IKILI...).
  // Kargo Icerigi doldur, Parcayi Kaydet butonuna bas
  // onComplete: parca kaydedildikten sonra cagrilir
  // =====================================================
  var KARGO_ICERIGI = "TOPUKLU AYAKKABI";

  function icerikDoldurVeKaydet(adet, onComplete) {
    // 1. Parca (koli) adedi -> 1
    var paketAdetInput = document.querySelector("#input-paket-adet");
    if (paketAdetInput && !paketAdetInput.disabled) {
      paketAdetInput.value = "1";
      paketAdetInput.dispatchEvent(new Event("input", { bubbles: true }));
      paketAdetInput.dispatchEvent(new Event("change", { bubbles: true }));
    }

    // 2. Kargo Icerigi (URUN tipli tanimlarda DHL alani gizler, icerigi kendisi koyar)
    var icerikDiv = document.querySelector("#divKargoIcerigi");
    var icerikInput = document.querySelector("#input-kargo-icerigi");
    if (icerikInput && !(icerikDiv && icerikDiv.hidden)) {
      icerikInput.value = KARGO_ICERIGI;
      // DHL'nin jQuery "input" dinleyicisi Parcayi Kaydet'i bununla aciyor
      icerikInput.dispatchEvent(new Event("input", { bubbles: true }));
      icerikInput.dispatchEvent(new Event("change", { bubbles: true }));
      console.log("[Gullu Asist] Kargo Icerigi yazildi: " + KARGO_ICERIGI);
    } else if (!icerikInput) {
      console.warn("[Gullu Asist] input-kargo-icerigi bulunamadi");
    }

    // 3. Parcayi Kaydet butonu — PARCA_KAYDET_BEKLEME_MS'ye kadar 250 ms'de bir yoklanir
    setTimeout(function() {
      var baslangic = Date.now();
      var deneme = 0;
      var bekleyici = setInterval(function() {
        deneme++;
        var btn = document.querySelector("#button-parca-ekle");
        if (btn && !btn.disabled) {
          clearInterval(bekleyici);
          btn.click();
          console.log("[Gullu Asist] Parcayi Kaydet tiklandi (" + deneme + ". deneme)");
          if (onComplete) onComplete(true);
        } else if (Date.now() - baslangic >= PARCA_KAYDET_BEKLEME_MS) {
          clearInterval(bekleyici);
          console.warn("[Gullu Asist] Parcayi Kaydet " + PARCA_KAYDET_BEKLEME_MS + " ms icinde aktif olmadi");
          showNotification("[UYARI] Parcayi Kaydet butonu aktif degil!", "#ffc107");
          if (onComplete) onComplete(false);
        }
      }, 250);
    }, 250);
  }

  chrome.runtime.onMessage.addListener(function(message) {
    if (message.kargoKodu) {
      console.log("[Gullu Asist] Mesaj geldi:", message.kargoKodu, "Urun:", message.urunAdet);
      var input = document.querySelector("#input-platform-kodu");

      if (!input) {
        console.warn("[Gullu Asist] input-platform-kodu bulunamadi.");
        showNotification("[HATA] Platform kodu alani bulunamadi!", "#dc3545");
        return;
      }

      if (input.disabled) {
        console.warn("[Gullu Asist] input-platform-kodu disabled durumda.");
        showNotification("[HATA] Once platform secimi yapin!", "#dc3545");
        return;
      }

      // Yazdirma checkbox'i tetiklemeden once aktif oldugundan emin ol
      yazdirmaCheckboxKoru();

      // Urun adedine gore dogru paketi sec, parca KAYDEDILDIKTEN sonra kargo kodu yaz
      var urunAdet = message.urunAdet || 1;
      urunPaketiSec(urunAdet, function(parcaKaydedildi) {
        if (!parcaKaydedildi) {
          showNotification("[HATA] Parca kaydedilemedi, kod gonderilmedi!", "#dc3545");
          return;
        }

        // Parca artik kayitli, simdi kargo kodunu yaz
        var nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
        nativeSetter.call(input, message.kargoKodu);
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));

        showNotification("[Gullu Asist] Kod yazildi: " + message.kargoKodu + " (" + urunAdet + " urun)", "#007bff");
        console.log("[Gullu Asist] Kod yazildi:", message.kargoKodu);

        setTimeout(function() {
          var hizliCheckbox = document.querySelector("#chkHizliEticaret");
          var isHizliMod = hizliCheckbox && hizliCheckbox.checked;

          if (isHizliMod) {
            var enterEvent = new KeyboardEvent("keyup", {
              bubbles: true,
              cancelable: true,
              key: "Enter",
              code: "Enter",
              keyCode: 13,
              which: 13
            });
            input.dispatchEvent(enterEvent);
            showNotification("[Gullu Asist] Hizli mod: Enter gonderildi", "#28a745");
            console.log("[Gullu Asist] Hizli mod: Enter keyup gonderildi.");
          } else {
            input.dispatchEvent(new Event("focusout", { bubbles: true }));
            showNotification("[Gullu Asist] Normal mod: focusout tetiklendi", "#28a745");
            console.log("[Gullu Asist] Normal mod: focusout tetiklendi.");
          }
        }, 300);
      });
    }
  });

  // =====================================================
  // 3) Arka plan sekmesi korumasi (Tab Freezing onleme)
  // =====================================================

  // Web Lock - Chrome sekmeyi uyutmasin
  if (navigator.locks) {
    navigator.locks.request("gullu-asist-dhl-keepalive", function() {
      return new Promise(function() {});
    });
  }

  // BroadcastChannel keepalive - arka planda timer'larin yavaslamasini onler
  try {
    var keepaliveChannel = new BroadcastChannel("gullu-asist-keepalive");
    setInterval(function() {
      keepaliveChannel.postMessage({ ping: Date.now() });
    }, 5000);
  } catch(e) {}

  // Worker-based timer - arka planda throttle edilmez
  // (Normal setInterval arka planda 1 dakikaya kadar yavaslatilabilir,
  //  Web Worker icindeki timer'lar throttle edilmez)
  try {
    var workerBlob = new Blob([
      'setInterval(function(){ postMessage("tick"); }, 10000);'
    ], { type: "application/javascript" });
    var keepaliveWorker = new Worker(URL.createObjectURL(workerBlob));
    keepaliveWorker.onmessage = function() {
      // Her tick'te sahte bir aktivite tetikle
      document.dispatchEvent(new MouseEvent("mousemove", {
        bubbles: true, cancelable: true,
        clientX: Math.random() * 200, clientY: Math.random() * 200
      }));
    };
    console.log("[Gullu Asist] Worker keepalive aktif");
  } catch(e) {
    // Worker olusturulamazsa eski yonteme geri don
    setInterval(function() {
      document.dispatchEvent(new MouseEvent("mousemove", {
        bubbles: true, cancelable: true,
        clientX: Math.random() * 200, clientY: Math.random() * 200
      }));
    }, 15000);
  }
}
