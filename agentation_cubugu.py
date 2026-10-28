"""
Agentation görsel geri bildirim çubuğu (https://github.com/benjitaylor/agentation).

Yalnızca SAHİP (users.is_owner) + 2FA'yı tamamlamış oturumda, her HTML sayfasının
sonuna enjekte edilir. Diğer kullanıcıların sayfasına tek satır bile gitmez.
React + paket tarayıcıda esm.sh'den yüklenir; panelde derleme adımı yok.
"""
from flask import Blueprint, current_app
from flask_login import current_user

from ai_asistan.blueprint import _tam_dogrulanmis_mi

agentation_bp = Blueprint("agentation", __name__)

_CUBUK_HTML = """
<div id="agentation-kok"></div>
<script type="module">
  import React from "https://esm.sh/react@18.3.1";
  import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";
  import { Agentation } from "https://esm.sh/agentation@3.1.2?deps=react@18.3.1,react-dom@18.3.1";
  createRoot(document.getElementById("agentation-kok"))
    .render(React.createElement(Agentation, { appName: "Güllü Panel" }));
</script>
"""


def _sahip_mi() -> bool:
    """Aktif kullanıcı tam doğrulanmış (login + 2FA) sahip mi?"""
    return _tam_dogrulanmis_mi() and bool(getattr(current_user, "is_owner", False))


@agentation_bp.after_app_request
def _cubuk_enjekte(response):
    """Sahibin gördüğü her HTML sayfasının son </body>'sinden önce çubuğu ekle."""
    try:
        if not _sahip_mi():
            return response
        ctype = response.headers.get("Content-Type", "")
        if "text/html" not in ctype or response.direct_passthrough:
            return response

        govde = response.get_data(as_text=True)
        if 'id="agentation-kok"' in govde:
            return response

        # İlk </body> inline JS string'i içinde olabilir (yazdırma fonksiyonları);
        # gerçek kapanış etiketini hedeflemek için rfind.
        idx = govde.rfind("</body>")
        if idx == -1:
            return response

        response.set_data(govde[:idx] + _CUBUK_HTML + "\n" + govde[idx:])
    except Exception:
        current_app.logger.exception("Agentation çubuğu enjeksiyonu başarısız")
    return response
