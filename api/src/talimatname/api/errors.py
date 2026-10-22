"""Hataların HTTP karşılığı: RFC 9457 problem+json (ADR-0014 md.8).

Alan hataları `domain/errors.py`'de tanımlıdır ve HTTP bilmez; burası
yalnızca eşlemeyi yapar. İstemci `type` alanına göre davranır, metne
göre değil: `title` Türkçe ve değişebilir, `type` sözleşmedir.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.domain.organization import ValidationError

PROBLEM_MEDIA_TYPE = "application/problem+json"
URN_PREFIX = "urn:talimatname:"

DURUM: dict[ErrorKind, int] = {
    "invalid": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "conflict": status.HTTP_409_CONFLICT,
    "not_found": status.HTTP_404_NOT_FOUND,
    "forbidden": status.HTTP_403_FORBIDDEN,
}


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
            status_code=DURUM[exc.kind],
            detail=exc.detail,
            instance=str(request.url.path),
            **exc.extra,
        )

    @app.exception_handler(ValidationError)
    async def _alan_dogrulama(request: Request, exc: ValidationError) -> JSONResponse:
        """Alan katmanının doğrulama hatası: alan adıyla birlikte döner."""
        return problem(
            code="gecersiz-istek",
            title="İstek doğrulanamadı",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            instance=str(request.url.path),
            errors=[{"alan": exc.field_name, "sebep": exc.message}],
        )

    @app.exception_handler(RequestValidationError)
    async def _sema_dogrulama(request: Request, exc: RequestValidationError) -> JSONResponse:
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
