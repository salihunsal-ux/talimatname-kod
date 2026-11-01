"""İstekten okunan "nereden" bilgisi: IP ve cihaz.

Uygulama fabrikasının içindeydi; hız sınırı da aynı IP'yi okumak
zorunda olduğu için ortaya alındı. İki ayrı okuma, bir gün ters vekil
yapılandırması değiştiğinde birinin düzeltilip ötekinin atlanması
demek olurdu.
"""

from __future__ import annotations

from fastapi import Request


def istemci_ip(request: Request) -> str | None:
    """Ters vekil arkasında gerçek istemci `X-Forwarded-For`un başında.

    Başlık **istemciden** gelebildiği için tek başına delil değil;
    günlüğe "istemcinin söylediği" olarak giriyor ve bu yüzden
    doğrulamada tek dayanak sayılmıyor. Hız sınırı için de aynı şey
    geçerli: başlığı değiştiren biri sınırı aşabilir — bu yüzden
    gerçek savunma ters vekilde (bkz. `hiz_siniri`).
    """
    iletilen = request.headers.get("x-forwarded-for")
    if iletilen:
        return iletilen.split(",")[0].strip()[:45] or None
    return request.client.host if request.client else None


def cihaz(request: Request) -> str | None:
    ajan = request.headers.get("user-agent")
    return ajan[:120] if ajan else None


__all__ = ["cihaz", "istemci_ip"]
