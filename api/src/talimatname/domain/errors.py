"""Alan hataları. HTTP bilmezler (ADR-0014 md.2: domain içe bağımlı değildir).

Her hatanın iki sözleşmesi var: `code` (makineye, istemci buna göre
davranır) ve `title` (kullanıcıya, Türkçe ve değişebilir). `kind`, sunum
katmanının HTTP durumunu seçmesi içindir — alan katmanı 409 ile 422
arasındaki farkı bilmek zorunda değil.
"""

from __future__ import annotations

from typing import Any, Literal

ErrorKind = Literal["invalid", "conflict", "not_found", "forbidden"]


class DomainError(Exception):
    code = "alan-hatasi"
    title = "İşlem kuralı gereği yapılamadı"
    kind: ErrorKind = "conflict"

    def __init__(self, detail: str | None = None, **extra: Any) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        self.extra = extra


class WindowClosed(DomainError):
    code = "pencere-kapali"
    title = "Pencere kapandı"
    kind: ErrorKind = "conflict"


class RunLocked(DomainError):
    code = "calistirma-kilitli"
    title = "Çalıştırmayı başka bir kullanıcı yapıyor"
    kind: ErrorKind = "conflict"


class EvidenceRequired(DomainError):
    code = "kanit-zorunlu"
    title = "Başarısız cevapta fotoğraf ve not zorunlu"
    kind: ErrorKind = "invalid"
