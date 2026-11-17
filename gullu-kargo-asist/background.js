// =====================================================
// Etiket PDF Kayit - Labelary API ile ZPL -> PDF
// Etiket boyutu: 100x100mm = 3.94x3.94 inch, 8 dpmm (203 dpi)
// Klasor: Downloads/DHL-Etiketler/etiketler-YYYY-MM-DD.pdf
// =====================================================
const LABELARY_URL = "https://api.labelary.com/v1/printers/8dpmm/labels/3.94x3.94/0/";
const PDF_KLASORU = "DHL-Etiketler";

function bugununAnahtari() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const g = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${g}`;
}

function uint8ToBase64(u8) {
  // Service worker'da btoa var ama buyuk array'lerde call stack overflow olmamasi icin parça parça
  let bin = "";
  const chunk = 0x8000;
  for (let i = 0; i < u8.length; i += chunk) {
    bin += String.fromCharCode.apply(null, u8.subarray(i, i + chunk));
  }
  return btoa(bin);
}

// ZPL islemleri sirayla calissin (race condition onleme)
let zplKuyruk = Promise.resolve();

async function zplIsleVeKaydet(zpl) {
  const tarih = bugununAnahtari();
  const storeKey = `zpl_${tarih}`;

  const data = await chrome.storage.local.get(storeKey);
  const mevcut = data[storeKey] || "";

  // Ayni ZPL zaten arsivdeyse atla (mukerrer yazdirma korumasi)
  if (mevcut && mevcut.indexOf(zpl) !== -1) {
    console.log("[Gullu Asist BG] ZPL zaten arsivde, atlandi");
    return;
  }

  const yeniArsiv = mevcut ? (mevcut + "\n" + zpl) : zpl;
  await chrome.storage.local.set({ [storeKey]: yeniArsiv });

  // Tum gunun ZPL'ini Labelary'ye gonder, multi-page PDF al
  let resp;
  try {
    resp = await fetch(LABELARY_URL, {
      method: "POST",
      headers: {
        "Accept": "application/pdf",
        "Content-Type": "application/x-www-form-urlencoded"
      },
      body: yeniArsiv
    });
  } catch (e) {
    console.error("[Gullu Asist BG] Labelary network hatasi:", e);
    return;
  }

  if (!resp.ok) {
    const txt = await resp.text().catch(() => "");
    console.error("[Gullu Asist BG] Labelary HTTP", resp.status, txt);
    return;
  }

  const ab = await resp.arrayBuffer();
  const u8 = new Uint8Array(ab);
  const dataUrl = "data:application/pdf;base64," + uint8ToBase64(u8);

  const filename = `${PDF_KLASORU}/etiketler-${tarih}.pdf`;
  try {
    await chrome.downloads.download({
      url: dataUrl,
      filename: filename,
      conflictAction: "overwrite",
      saveAs: false
    });
    console.log("[Gullu Asist BG] PDF guncellendi:", filename, "(" + u8.length + " bytes)");
  } catch (e) {
    console.error("[Gullu Asist BG] Download hatasi:", e);
  }
}

// Kargo kodu ve urun adet mesajini DHL sekmesine ilet
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.kargoKodu) {
    chrome.tabs.query({ url: "*://onlinesube.dhlecommerce.com.tr/*" }, (tabs) => {
      for (let tab of tabs) {
        chrome.tabs.sendMessage(tab.id, {
          kargoKodu: message.kargoKodu,
          urunAdet: message.urunAdet || 1
        });
        console.log("📨 [Background] DHL sekmesine gonderildi - Kod:", message.kargoKodu, "Adet:", message.urunAdet);
      }
    });
  }

  if (message.zplCapture && typeof message.zplCapture === "string") {
    const zpl = message.zplCapture;
    zplKuyruk = zplKuyruk
      .then(() => zplIsleVeKaydet(zpl))
      .catch((e) => console.error("[Gullu Asist BG] ZPL isleme hatasi:", e));
  }
});

// DHL sekmesini uyandirmak icin her 25 saniyede bir ping gonder
// (Chrome minimum alarm suresi 30sn, ama 0.5dk daha guvenli)
chrome.alarms.create("dhl-keepalive", { periodInMinutes: 0.5 });

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "dhl-keepalive") {
    chrome.tabs.query({ url: "*://onlinesube.dhlecommerce.com.tr/*" }, (tabs) => {
      for (let tab of tabs) {
        // Sekmeyi uyandir ve yazdirma checkbox'ini koru
        chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: () => {
            // Sahte aktivite
            document.dispatchEvent(new MouseEvent("mousemove", {
              bubbles: true, clientX: Math.random() * 100, clientY: Math.random() * 100
            }));

            // Yazdirma checkbox kontrolu
            var cb = document.querySelector("#checkbox-her-gonderi-sonrasinda-yazdir");
            if (cb && !cb.checked) {
              cb.checked = true;
              console.log("[Gullu Asist BG] Yazdirma checkbox yeniden aktif edildi");
            }
          }
        }).catch(() => { /* sekme kapanmissa sorun degil */ });
      }
    });
  }
});
