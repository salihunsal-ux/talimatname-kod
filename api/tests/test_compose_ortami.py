"""Compose'un uygulamaya verdiği ortam Settings tarafından okunabiliyor mu.

İddia: **`docker compose up` diyen biri açılışta patlamamalı.**

Dağıtımın ilk koşusunda iki kez aynı cinsten hata çıktı: belgelerde
yazan ortam biçimi (`CORS_ORIGINS=a,b`, tek satırlık PEM) kodun kabul
ettiği biçim değildi. Her ikisi de ancak kaplar ayağa kalkınca,
dakikalar sonra görüldü. Bu test aynı soruyu saniyede sorar: compose
dosyasındaki `x-api-ortam` bloğu gerçekten geçerli bir yapılandırma
mı.

Gerçek sır yok: `${VAR:?...}` biçimindeki zorunlu alanlar testin
ürettiği sahte değerlerle doldurulur (ADR-0012 md.3).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from talimatname.settings import Settings

COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"

#: `${AD}`, `${AD:-varsayılan}`, `${AD:?hata}`
DEGISKEN = re.compile(r"\$\{([A-Z0-9_]+)(?::([-?])([^}]*))?\}")

#: Zorunlu alanlar için testin ürettiği sahte değerler. Bir alan
#: burada yoksa genel bir dize verilir.
#: `.env` tek satırlık: PEM kaçışla yazılır, uygulama okurken açar.
SAHTE_PEM = "-----BEGIN {0} KEY-----\\ngovde\\n-----END {0} KEY-----"

SAHTE = {
    "POSTGRES_PASSWORD": "sahte-parola",
    "OBJECT_STORE_SECRET_KEY": "sahte-gizli",
    "JWT_PRIVATE_KEY": SAHTE_PEM.format("PRIVATE"),
    "JWT_PUBLIC_KEY": SAHTE_PEM.format("PUBLIC"),
}


def _coz(deger: Any) -> str:
    """Compose'un değişken yerine koymasını taklit eder."""

    def tek(eslesme: re.Match[str]) -> str:
        ad, isaret, kuyruk = eslesme.group(1), eslesme.group(2), eslesme.group(3)
        if isaret == "-":  # ${AD:-varsayılan}
            return kuyruk
        return SAHTE.get(ad, f"sahte-{ad.lower()}")

    return DEGISKEN.sub(tek, str(deger))


def _api_ortami() -> dict[str, str]:
    belge = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    ham = belge["x-api-ortam"]
    return {ad: _coz(deger) for ad, deger in ham.items()}


def test_compose_ortamiyla_ayarlar_acilir(monkeypatch: pytest.MonkeyPatch) -> None:
    ortam = _api_ortami()
    assert ortam, "x-api-ortam boş: compose dosyası değişmiş olmalı"
    for ad, deger in ortam.items():
        monkeypatch.setenv(ad, deger)

    ayar = Settings(_env_file=None)  # type: ignore[call-arg]

    # Compose yığını kendi veritabanını ve kovasını veriyor: uygulama
    # sessizce yerel dizine ya da geçici anahtara düşmemeli.
    assert ayar.database_url
    assert ayar.object_store_configured
    assert ayar.jwt_private_key
    assert ayar.jwt_public_key


def test_compose_pem_kacisi_cozulur(monkeypatch: pytest.MonkeyPatch) -> None:
    """`.env` tek satırlık; PEM kaçışı okunurken açılmalı."""
    for ad, deger in _api_ortami().items():
        monkeypatch.setenv(ad, deger)

    ozel = Settings(_env_file=None).jwt_private_key  # type: ignore[call-arg]

    assert ozel is not None
    assert chr(10) in ozel, "PEM tek satır kalmış: imza anahtarı geçersiz olurdu"
