"""MNG ApiZone kimlik ve ortam ayarları (.env).

Ortam seçimi: MNG_ORTAM=sandbox|prod (varsayılan sandbox — prod kimliği girilmeden
canlıda gönderi açılmasın).

  sandbox: MNG_SANDBOX_BASE_URL, MNG_SANDBOX_CLIENT_ID, MNG_SANDBOX_CLIENT_SECRET,
           MNG_SANDBOX_CUSTOMER_NUMBER, MNG_SANDBOX_PASSWORD
  prod:    MNG_BASE_URL, MNG_CLIENT_ID, MNG_CLIENT_SECRET,
           MNG_CUSTOMER_NUMBER, MNG_PASSWORD

Köprü servisin config.json'ındaki mng (test) / mngProd (canlı) bloklarıyla birebir.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

SANDBOX_BASE_URL = "https://testapi.mngkargo.com.tr/mngapi/api"
PROD_BASE_URL = "https://api.mngkargo.com.tr/mngapi/api"
GECERLI_ORTAMLAR = ("sandbox", "prod")


@dataclass(frozen=True)
class MngAyar:
    ortam: str
    base_url: str
    client_id: str
    client_secret: str
    customer_number: str
    password: str
    identity_type: int = 1

    @property
    def hazir(self) -> bool:
        return all((self.base_url, self.client_id, self.client_secret,
                    self.customer_number, self.password))

    @property
    def sandbox(self) -> bool:
        return self.ortam == "sandbox"

    @classmethod
    def from_env(cls, ortam: str | None = None) -> "MngAyar":
        ortam = (ortam or os.getenv("MNG_ORTAM") or "sandbox").strip().lower()
        if ortam not in GECERLI_ORTAMLAR:
            raise ValueError(f"MNG_ORTAM geçersiz: {ortam!r} (sandbox | prod)")
        onek = "MNG_SANDBOX_" if ortam == "sandbox" else "MNG_"
        varsayilan_url = SANDBOX_BASE_URL if ortam == "sandbox" else PROD_BASE_URL
        return cls(
            ortam=ortam,
            base_url=(os.getenv(f"{onek}BASE_URL") or varsayilan_url).rstrip("/"),
            client_id=(os.getenv(f"{onek}CLIENT_ID") or "").strip(),
            client_secret=(os.getenv(f"{onek}CLIENT_SECRET") or "").strip(),
            customer_number=(os.getenv(f"{onek}CUSTOMER_NUMBER") or "").strip(),
            password=(os.getenv(f"{onek}PASSWORD") or "").strip(),
        )
