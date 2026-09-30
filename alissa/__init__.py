# -*- coding: utf-8 -*-
"""Muhammet ALİSSA hesabı — tedarikçinin Trendyol satışlarının haftalık hakedişi.

Mevcut panelden bağımsızdır: kendi tabloları (alissa_*), kendi Trendyol istemcisi.
Veri panelin sipariş tablolarından DEĞİL, Trendyol'un güncel servislerinden gelir
(finans settlements, kesinti faturaları, kargo faturası kalemleri, sipariş v2).
Panelden okunan tek şey: hangi barkodların Alissa'ya ait olduğu (products.tedarikci_kodu).

Kurulum: DISABLE_JOBS=1 python -m alissa.kur
"""
