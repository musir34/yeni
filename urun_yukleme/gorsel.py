# -*- coding: utf-8 -*-
"""
Ürün görsellerini Shopify CDN'e taşıma (Trendyol HTTPS görsel şartı için).

Akış (elle yapılan yüklemelerde kanıtlandı):
stagedUploadsCreate → imzalı POST ile dosya yükleme → fileCreate → READY olunca
cdn.shopify.com adresi. Trendyol görseli bu adresten kendi CDN'ine kopyalar.
"""
import logging
import mimetypes
import os
import time

import requests

from shopify_site.shopify_config import ShopifyConfig

logger = logging.getLogger(__name__)


def _graphql(query: str, variables: dict) -> dict:
    r = requests.post(ShopifyConfig.graphql_url(),
                      json={"query": query, "variables": variables},
                      headers=ShopifyConfig.get_headers(), timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(f"Shopify GraphQL: {data['errors']}")
    return data["data"]


def cdn_yukle(dosyalar: list[tuple[str, str]]) -> list[str]:
    """
    [(cdn_dosya_adi, yerel_yol)] listesini Shopify CDN'e taşır;
    aynı sırada HTTPS URL listesi döner.
    """
    if not dosyalar:
        return []

    girdiler = []
    for ad, yol in dosyalar:
        mime = mimetypes.guess_type(ad)[0] or "image/jpeg"
        girdiler.append({"resource": "IMAGE", "filename": ad, "mimeType": mime,
                         "httpMethod": "POST", "fileSize": str(os.path.getsize(yol))})

    d = _graphql("""
        mutation stagedUploadsCreate($input: [StagedUploadInput!]!) {
          stagedUploadsCreate(input: $input) {
            stagedTargets { url resourceUrl parameters { name value } }
            userErrors { field message }
          }
        }""", {"input": girdiler})
    hedefler = d["stagedUploadsCreate"]["stagedTargets"]
    hatalar = d["stagedUploadsCreate"]["userErrors"]
    if hatalar:
        raise RuntimeError(f"stagedUploadsCreate: {hatalar}")

    # İmzalı POST ile dosyaları yükle (parametre sırası korunmalı, dosya en sonda)
    for (ad, yol), hedef in zip(dosyalar, hedefler):
        mime = mimetypes.guess_type(ad)[0] or "image/jpeg"
        alanlar = [(p["name"], (None, p["value"])) for p in hedef["parameters"]]
        with open(yol, "rb") as f:
            alanlar.append(("file", (ad, f, mime)))
            r = requests.post(hedef["url"], files=alanlar, timeout=120)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Görsel yüklenemedi ({ad}): HTTP {r.status_code}")
        logger.info("[URUN-GORSEL] %s staged alana yüklendi", ad)

    # fileCreate → kalıcı CDN dosyası
    d = _graphql("""
        mutation fileCreate($files: [FileCreateInput!]!) {
          fileCreate(files: $files) {
            files { id fileStatus }
            userErrors { field message }
          }
        }""", {"files": [{"originalSource": h["resourceUrl"], "contentType": "IMAGE",
                          "alt": ad} for (ad, _), h in zip(dosyalar, hedefler)]})
    if d["fileCreate"]["userErrors"]:
        raise RuntimeError(f"fileCreate: {d['fileCreate']['userErrors']}")
    kimlikler = [f["id"] for f in d["fileCreate"]["files"]]

    # READY olana dek bekle, CDN URL'lerini topla
    for _ in range(20):
        time.sleep(3)
        d = _graphql("""
            query getFiles($ids: [ID!]!) {
              nodes(ids: $ids) { ... on MediaImage { id fileStatus image { url } } }
            }""", {"ids": kimlikler})
        dugumler = [n for n in d["nodes"] if n]
        if all(n.get("fileStatus") == "READY" and (n.get("image") or {}).get("url")
               for n in dugumler) and len(dugumler) == len(kimlikler):
            sirali = {n["id"]: n["image"]["url"] for n in dugumler}
            return [sirali[k] for k in kimlikler]
        if any(n.get("fileStatus") == "FAILED" for n in dugumler):
            raise RuntimeError("Shopify görsel işleme FAILED döndü.")
    raise RuntimeError("Görseller CDN'de zamanında READY olmadı.")
