"""Hata biçimi: RFC 9457 problem+json (ADR-0014 md.8).

İstemci `type` alanına göre davranır, metne göre değil: `title` Türkçe ve
değişebilir, `type` sözleşmedir.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

PROBLEM_MEDIA_TYPE = "application/problem+json"
URN_PREFIX = "urn:talimatname:"


class DomainError(Exception):
    """Alan kuralı ihlali. `code` makine sözleşmesidir, `title` kullanıcıya gider."""

    status_code = status.HTTP_409_CONFLICT
    code = "alan-hatasi"
    title = "İşlem kuralı gereği yapılamadı"

    def __init__(self, detail: str | None = None, **extra: Any) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        self.extra = extra


class WindowClosed(DomainError):
    code = "pencere-kapali"
    title = "Pencere kapandı"
    status_code = status.HTTP_409_CONFLICT


class RunLocked(DomainError):
    code = "calistirma-kilitli"
    title = "Çalıştırmayı başka bir kullanıcı yapıyor"
    status_code = status.HTTP_409_CONFLICT


class EvidenceRequired(DomainError):
    code = "kanit-zorunlu"
    title = "Başarısız cevapta fotoğraf ve not zorunlu"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT


def problem(
    *,
    code: str,
    title: str,
    status_code: int,
    detail: str | None = None,
    instance: str | None = None,
    **extra: Any,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": URN_PREFIX + code,
        "title": title,
        "status": status_code,
    }
    if detail:
        body["detail"] = detail
    if instance:
        body["instance"] = instance
    body.update(extra)
    return JSONResponse(body, status_code=status_code, media_type=PROBLEM_MEDIA_TYPE)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:
        return problem(
            code=exc.code,
            title=exc.title,
            status_code=exc.status_code,
            detail=exc.detail,
            instance=str(request.url.path),
            **exc.extra,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        alanlar = [
            {"alan": ".".join(str(p) for p in hata["loc"][1:]), "sebep": hata["msg"]}
            for hata in exc.errors()
        ]
        return problem(
            code="gecersiz-istek",
            title="İstek doğrulanamadı",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            instance=str(request.url.path),
            errors=alanlar,
        )
