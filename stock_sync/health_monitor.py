"""Shopify stok senkronizasyon sağlık izleme.

İki ayrı kontrol:
  1. check_sync_staleness — senkron donduysa / eski kalmışsa uyarı
  2. check_oversell_risk  — Shopify'da satılabilir görünen ama panelde stoğu olmayan
                            ürünler varsa uyarı

Her ikisi de `mail_service.notify` ile ilgili olay için abone olan kullanıcılara
e-posta gönderir. Kullanıcı yönetiminden (kullanıcı düzenleme → notify_events)
her kişi açıp kapatılabilir.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# Eşik değerleri — aşılırsa uyarı gönderilir
STALE_SYNC_DAYS = 2           # Son sync'ten kaç gün geçerse "stale" sayılır
STALE_COUNT_ALERT = 20        # Kaç stale mapping olursa uyarı gönderilir
MISMATCH_ALERT_THRESHOLD = 150 # Kaç tutarsız mapping olursa uyarı gönderilir (15dk sync penceresinde gelen normal siparişlerin üstünde olmalı)
OVERSELL_ALERT_THRESHOLD = 1  # Oversell riski tespit edilirse hep uyarı (min 1)


def check_sync_staleness() -> Dict[str, Any]:
    """Donmuş veya tutarsız mapping'leri tespit et, eşik aşılırsa mail gönder."""
    from models import db, ShopifyMapping, CentralStock
    from mail_service import notify, build_alert_email_html

    cutoff = datetime.utcnow() - timedelta(days=STALE_SYNC_DAYS)

    stale_q = ShopifyMapping.query.filter(
        (ShopifyMapping.last_sync_at.is_(None)) | (ShopifyMapping.last_sync_at < cutoff)
    )
    stale_count = stale_q.count()

    mismatches: List[Dict[str, Any]] = []
    rows = db.session.query(ShopifyMapping, CentralStock).outerjoin(
        CentralStock, CentralStock.barcode == ShopifyMapping.barcode
    ).all()
    for m, cs in rows:
        panel = cs.qty if cs else 0
        sent = m.last_stock_sent if m.last_stock_sent is not None else -1
        if panel != sent:
            mismatches.append({
                "barkod": m.barcode,
                "panel": panel,
                "shopify": sent,
                "note": (m.last_sync_at.strftime("%Y-%m-%d %H:%M")
                         if m.last_sync_at else "hiç sync olmamış"),
            })

    logger.info(
        "[HEALTH] Stale mapping: %d (>%d gün), tutarsız: %d",
        stale_count, STALE_SYNC_DAYS, len(mismatches),
    )

    should_alert = stale_count >= STALE_COUNT_ALERT or len(mismatches) >= MISMATCH_ALERT_THRESHOLD
    if not should_alert:
        return {"alerted": False, "stale_count": stale_count, "mismatch_count": len(mismatches)}

    # En problemli ilk 30 kaydı göster (en eski sync olanlar)
    mismatches.sort(key=lambda d: d["note"])
    total_mappings = ShopifyMapping.query.count()

    headline = (
        f"{stale_count} mapping son {STALE_SYNC_DAYS} gündür güncellenmedi, "
        f"{len(mismatches)} mapping'de panel ↔ Shopify tutarsızlığı var."
    )
    summary_rows: List[Tuple[str, str]] = [
        ("Toplam mapping", str(total_mappings)),
        (f"Son {STALE_SYNC_DAYS}+ gündür sync olmamış", str(stale_count)),
        ("Panel ↔ Shopify tutarsız", str(len(mismatches))),
        ("Kontrol zamanı", datetime.now().strftime("%Y-%m-%d %H:%M")),
    ]
    action = (
        "Panel → Ayarlar → Shopify Stok Senkronu'ndan manuel 'Stok Gönder' çalıştırın. "
        "Sorun tekrar ediyorsa _send_stock_batch log'larına bakın: "
        "<code>grep SHOPIFY logs/app.log | tail -50</code>"
    )
    body = build_alert_email_html(
        event="stock_sync_stale",
        headline=headline,
        summary_rows=summary_rows,
        detail_rows=mismatches,
        action_hint=action,
    )
    notify("stock_sync_stale",
           subject=f"[STOK SYNC] {len(mismatches)} tutarsız, {stale_count} stale mapping",
           body=body)
    return {
        "alerted": True,
        "stale_count": stale_count,
        "mismatch_count": len(mismatches),
    }


def check_oversell_risk() -> Dict[str, Any]:
    """
    Panel stoğu 0 ama Shopify'a son 'var' olarak gönderilmiş ürünleri tespit et.
    Canlı Shopify envanterini sorgulamak ağır; burada sadece DB üzerinde
    last_stock_sent > 0 AND CentralStock.qty == 0 koşulunu tarıyoruz.
    """
    from models import db, ShopifyMapping, CentralStock
    from mail_service import notify, build_alert_email_html

    risk_rows: List[Dict[str, Any]] = []
    rows = db.session.query(ShopifyMapping, CentralStock).outerjoin(
        CentralStock, CentralStock.barcode == ShopifyMapping.barcode
    ).filter(ShopifyMapping.last_stock_sent > 0).all()
    for m, cs in rows:
        panel = cs.qty if cs else 0
        if panel == 0 and (m.last_stock_sent or 0) > 0:
            risk_rows.append({
                "barkod": m.barcode,
                "panel": 0,
                "shopify": m.last_stock_sent,
                "note": (m.shopify_product_title or "")[:60],
            })

    logger.info("[HEALTH] Oversell riski: %d mapping", len(risk_rows))

    if len(risk_rows) < OVERSELL_ALERT_THRESHOLD:
        return {"alerted": False, "count": len(risk_rows)}

    risk_rows.sort(key=lambda d: -int(d.get("shopify") or 0))
    headline = (
        f"{len(risk_rows)} üründe panel stoğu 0 fakat Shopify'da satılabilir görünüyor. "
        "Yeni sipariş gelirse oversell olur."
    )
    summary_rows: List[Tuple[str, str]] = [
        ("Riskli ürün sayısı", str(len(risk_rows))),
        ("Kontrol zamanı", datetime.now().strftime("%Y-%m-%d %H:%M")),
    ]
    action = (
        "Bu ürünlerin Shopify stoğunu manuel 0'a çekin veya bir sonraki "
        "otomatik sync (15 dk) düzeltecektir. Aynı barkod sürekli listelenir ise "
        "variant Shopify'da manuel override edilmiş olabilir."
    )
    body = build_alert_email_html(
        event="shopify_oversell_risk",
        headline=headline,
        summary_rows=summary_rows,
        detail_rows=risk_rows,
        action_hint=action,
    )
    notify("shopify_oversell_risk",
           subject=f"[OVERSELL RİSKİ] {len(risk_rows)} ürün panel=0 ama Shopify'da satışta",
           body=body)
    return {"alerted": True, "count": len(risk_rows)}


def run_all_checks() -> Dict[str, Any]:
    """Tüm kontrolleri sıra ile çalıştır. Scheduler bunu çağırır."""
    results: Dict[str, Any] = {}
    try:
        results["sync_staleness"] = check_sync_staleness()
    except Exception as exc:
        logger.error("[HEALTH] check_sync_staleness hata: %s", exc, exc_info=True)
        results["sync_staleness"] = {"error": str(exc)}

    try:
        results["oversell_risk"] = check_oversell_risk()
    except Exception as exc:
        logger.error("[HEALTH] check_oversell_risk hata: %s", exc, exc_info=True)
        results["oversell_risk"] = {"error": str(exc)}

    return results
