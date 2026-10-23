"""Test ortamı: `db` işaretlisi olmayan her test **bellek içi** koşar.

Gerekçe: uç nokta testleri paylaşılan geliştirme veritabanına yazmamalı
(hem yavaş hem kirletici). Veritabanı davranışını `@pytest.mark.db`
işaretli testler ölçüyor.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from talimatname.api import bagimliliklar
from talimatname.settings import get_settings

_DEPOLAR = (
    bagimliliklar._org_deposu,
    bagimliliklar._kullanici_deposu,
    bagimliliklar._sablon_deposu,
    bagimliliklar._plan_deposu,
    bagimliliklar._cevap_deposu,
    bagimliliklar._aksiyon_deposu,
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
