"""Uygulama fabrikası. Tek bir global `app` yok: test ayarlarıyla kurulabilir."""

from __future__ import annotations

import logging
from typing import Any, Literal

import structlog
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from talimatname import __version__
from talimatname.api.bagimliliklar import ayarlari_kullan
from talimatname.api.errors import register_error_handlers
from talimatname.api.istek import cihaz, istemci_ip
from talimatname.api.routers import (
    actions,
    auth,
    ciktilar,
    dashboard,
    dogrulama,
    evidence,
    execution,
    notifications,
    organization,
    plans,
    reports,
    setup,
    sync,
    templates,
    users,
)
from talimatname.services.audit import RequestContext, using_context
from talimatname.settings import Settings, get_settings

API_PREFIX = "/api/v1"


def configure_logging(level: str) -> None:
    """JSON günlük: her satırda istek kimliği ve kiracı olacak şekilde (ADR-0014 md.1)."""
    logging.basicConfig(format="%(message)s", level=getattr(logging, level.upper(), logging.INFO))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


class HealthResponse(BaseModel):
    """Canlılık yanıtı. Şema açıkça tanımlı: istemci tipleri bundan üretilir."""

    status: Literal["ok"] = "ok"
    version: str = Field(description="API sürümü")
    environment: str = Field(description="dev | test | staging | prod")
    database_configured: bool = Field(description="DATABASE_URL tanımlı mı")
    object_store_configured: bool = Field(
        description="Nesne depolama **tam** yapılandırılmış mı (uç nokta, kova, anahtarlar)"
    )
    timestamping_configured: bool = Field(
        description=(
            "Günlük kökü dış zaman damgasına çıpalanıyor mu (FR-1302). "
            "Kapalıyken zincir yalnızca tek tek değişiklikleri görünür kılar."
        )
    )


def build_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix=API_PREFIX)

    @router.get("/health", tags=["sistem"], summary="Canlılık ve yapılandırma özeti")
    def health() -> HealthResponse:
        """Sürüm, ortam ve bağımlılıkların yapılandırılmış olup olmadığı.

        Veritabanına **bağlanmaz**: canlılık kontrolü bağımlılıkların
        durumuna göre kırmızı olmamalı (hazırlık kontrolü ayrı gelecek).
        """
        return HealthResponse(
            version=__version__,
            environment=settings.environment,
            database_configured=settings.database_url is not None,
            object_store_configured=settings.object_store_configured,
            timestamping_configured=settings.timestamping_configured,
        )

    router.include_router(auth.router)
    router.include_router(organization.router)
    router.include_router(users.router)
    router.include_router(templates.router)
    router.include_router(plans.router)
    router.include_router(dashboard.router)
    router.include_router(actions.router)
    router.include_router(notifications.router)
    router.include_router(execution.router)
    router.include_router(evidence.router)
    router.include_router(sync.router)
    router.include_router(setup.router)
    router.include_router(reports.router)
    router.include_router(ciktilar.router)
    # Oturumsuz: kâğıdı eline alan denetçi panele giremez (FR-1218).
    router.include_router(dogrulama.router)
    return router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    ayarlari_kullan(settings)
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Talimatname API",
        version=__version__,
        description=(
            "Kanıtlı görev listesi API'si (v1 çekirdek). "
            "Hatalar RFC 9457 problem+json biçiminde döner."
        ),
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        )

    @app.middleware("http")
    async def izi_baglami(request: Request, sonraki: Any) -> Any:
        """Olay günlüğünün "nereden" kısmı (FR-1301).

        Burada kuruluyor çünkü IP ve cihaz yalnızca HTTP katmanında
        biliniyor; olayı yazan yer ise servisin derinliği. Aktör
        henüz belli değil — belirteç çözüldüğünde ekleniyor
        (`guvenlik.gecerli_kullanici`).
        """
        with using_context(RequestContext(ip=istemci_ip(request), device=cihaz(request))):
            return await sonraki(request)

    register_error_handlers(app)
    app.include_router(build_router(settings))
    return app
