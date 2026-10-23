"""Uygulama fabrikası ve hata biçimi testleri."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from talimatname.api.app import create_app
from talimatname.api.errors import PROBLEM_MEDIA_TYPE
from talimatname.domain.errors import WindowClosed
from talimatname.settings import Settings


def _istemci(**ayar: object) -> TestClient:
    return TestClient(create_app(Settings(**ayar)))  # type: ignore[arg-type]


def test_health_veritabani_olmadan_calisir() -> None:
    """Ortam adı **açıkça** verilir: test, ortam değişkenine bağlı olmamalı.

    (CI `ENVIRONMENT=test` ile koşuyor; varsayılanı sabit sanmak testi
    makineye bağlar.)
    """
    yanit = _istemci(environment="dev").get("/api/v1/health")
    assert yanit.status_code == 200
    govde = yanit.json()
    assert govde["status"] == "ok"
    assert govde["environment"] == "dev"
    assert govde["database_configured"] is False


def test_health_veritabani_yapilandirilmis() -> None:
    yanit = _istemci(database_url="postgresql://x/y").get("/api/v1/health")
    assert yanit.json()["database_configured"] is True


def test_openapi_uretiliyor() -> None:
    yanit = _istemci().get("/api/v1/openapi.json")
    assert yanit.status_code == 200
    assert "/api/v1/health" in yanit.json()["paths"]


def test_alan_hatasi_problem_json_doner() -> None:
    """ADR-0014 md.8: hata gövdesi type/title/status taşır, medya tipi problem+json."""
    app = create_app(Settings())

    @app.get("/api/v1/_test_hata")
    def _hata() -> None:
        raise WindowClosed("22:00-01:30 penceresi kapandı", window_end="2026-11-02T22:30:00Z")

    yanit = TestClient(app, raise_server_exceptions=False).get("/api/v1/_test_hata")
    assert yanit.status_code == 409
    assert yanit.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    govde = yanit.json()
    assert govde["type"] == "urn:talimatname:pencere-kapali"
    assert govde["title"] == "Pencere kapandı"
    assert govde["window_end"] == "2026-11-02T22:30:00Z"


def test_cors_yalnizca_yapilandirilmis_kaynaga_izin_verir() -> None:
    """Panel tarayıcıdan çağırabilsin diye CORS açık; joker kaynak yasak."""
    app = create_app(Settings(cors_origins=["http://localhost:5173"]))
    istemci = TestClient(app)

    izinli = istemci.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert izinli.headers["access-control-allow-origin"] == "http://localhost:5173"

    yabanci = istemci.get("/api/v1/health", headers={"Origin": "https://baska.example"})
    assert "access-control-allow-origin" not in yabanci.headers


def test_joker_cors_kabul_edilmez() -> None:
    with pytest.raises(RuntimeError, match="joker"):
        Settings(cors_origins=["*"])


def test_prod_ortaminda_eksik_ayar_uygulamayi_acmaz() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        Settings(environment="prod")
