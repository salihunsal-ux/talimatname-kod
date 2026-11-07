"""Alan hataları. HTTP bilmezler (ADR-0014 md.2: domain içe bağımlı değildir).

Her hatanın iki sözleşmesi var: `code` (makineye, istemci buna göre
davranır) ve `title` (kullanıcıya, Türkçe ve değişebilir). `kind`, sunum
katmanının HTTP durumunu seçmesi içindir — alan katmanı 409 ile 422
arasındaki farkı bilmek zorunda değil.
"""

from __future__ import annotations

from typing import Any, Literal

#: `too_many`: oturumsuz uç noktaların hız sınırı (FR-1218). Sunum
#: katmanı 429'a çeviriyor; alan katmanı sayıyı bilmiyor.
ErrorKind = Literal["invalid", "conflict", "not_found", "forbidden", "too_many"]


class DomainError(Exception):
    code = "alan-hatasi"
    title = "İşlem kuralı gereği yapılamadı"
    kind: ErrorKind = "conflict"
    #: Hangi girdi alanı reddedildi. Dolu olduğunda cevaba `errors`
    #: giriyor ve form hatayı o alanın yanına yazabiliyor; yoksa
    #: kullanıcı cümleyi okuyup formu gözle arıyor (bağımsız test
    #: turu D-4). Alanı olmayan kural hataları için `None` doğru.
    field: str | None = None

    def __init__(self, detail: str | None = None, **extra: Any) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        if self.field is not None and "errors" not in extra:
            extra["errors"] = [{"alan": self.field, "sebep": self.title}]
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
