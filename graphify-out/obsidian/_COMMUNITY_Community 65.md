---
type: community
cohesion: 0.15
members: 15
---

# Community 65

**Cohesion:** 0.15 - loosely connected
**Members:** 15 nodes

## Members
- [[Cihaz limitini kontrol eder. (izin_var, mesaj) döner.]] - rationale - login_logout.py
- [[Kayıtlı (güvenilen) cihaz. Cookie token ile eşleşir.]] - rationale - models.py
- [[User-Agent'tan cihaz tipini belirler 'mobile' veya 'pc'.]] - rationale - login_logout.py
- [[User-Agent'tan okunabilir cihaz adı çıkarır.]] - rationale - login_logout.py
- [[UserDevice]] - code - models.py
- [[Yeni cihaz kaydeder ve çerez ayarlar.]] - rationale - login_logout.py
- [[_check_device_limit()]] - code - login_logout.py
- [[_detect_device_name()]] - code - login_logout.py
- [[_detect_device_type()]] - code - login_logout.py
- [[_get_trusted_device()]] - code - login_logout.py
- [[_register_device()]] - code - login_logout.py
- [[login()]] - code - login_logout.py
- [[login_user()]] - code - login_logout.py
- [[verify_totp()]] - code - login_logout.py
- [[İstekteki çerezden güvenilen cihazı döner (varsa).]] - rationale - login_logout.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Community_65
SORT file.name ASC
```

## Connections to other communities
- 12 edges to [[_COMMUNITY_Akıllı Motor (İndirim & Fiyat)]]
- 2 edges to [[_COMMUNITY_Community 57]]
- 1 edge to [[_COMMUNITY_Community 66]]

## Top bridge nodes
- [[_register_device()]] - degree 8, connects to 2 communities
- [[UserDevice]] - degree 5, connects to 2 communities
- [[_check_device_limit()]] - degree 4, connects to 2 communities
- [[login()]] - degree 6, connects to 1 community
- [[_detect_device_type()]] - degree 4, connects to 1 community