"""Test ortamı: `db` işaretlisi olmayan her test **bellek içi** koşar.

Gerekçe: uç nokta testleri paylaşılan geliştirme veritabanına yazmamalı
(hem yavaş hem kirletici). Veritabanı davranışını `@pytest.mark.db`
işaretli testler ölçüyor.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from talimatname.api import bagimliliklar
from talimatname.settings import get_settings

_DEPOLAR = (
    bagimliliklar._org_deposu,
    bagimliliklar._kullanici_deposu,
    bagimliliklar._sablon_deposu,
    bagimliliklar._plan_deposu,
    bagimliliklar._cevap_deposu,
    bagimliliklar._aksiyon_deposu,
    bagimliliklar._kimlik_servisi,
)


def _temizle() -> None:
    get_settings.cache_clear()
    for depo in _DEPOLAR:
        depo.cache_clear()
    bagimliliklar._ilk_tur_kosuldu = False


@pytest.fixture(autouse=True)
def bellek_modu(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    if request.node.get_closest_marker("db"):
        yield
        return
    monkeypatch.setenv("DATABASE_URL", "")
    _temizle()
    yield
    _temizle()


#: Tohumdaki örnek kullanıcıların telefonları (adlar uydurmadır, ADR-0003).
TELEFON = {
    "admin": "+905321110001",
    "region_manager": "+905321110002",  # Anadolu bölgesi
    "branch_manager": "+905321110003",  # Kadıköy
    "staff": "+905321110005",  # Kadıköy
}


def oturum_ac(istemci: TestClient, rol: str = "admin") -> TestClient:
    """İstemciye o rolün belirtecini takar ve aynı istemciyi döndürür.

    Kod isteme/doğrulama akışının kendisi `test_auth.py`de sınanıyor.
    Buradaki uç nokta testleri yetkilendirmeyi değil davranışı ölçtüğü
    için belirteç doğrudan kimlik servisinden alınıyor: SMS yok, kod yok.
    """
    kullanici = bagimliliklar._kullanici_deposu().user_by_phone(TELEFON[rol])
    assert kullanici is not None, f"tohumda {rol} yok"
    belirtec = bagimliliklar.kimlik_servisi().issue_token(kullanici)
    istemci.headers["Authorization"] = f"Bearer {belirtec}"
    return istemci
