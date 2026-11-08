"""Test ortamı: `db` işaretlisi olmayan her test **bellek içi** koşar.

Gerekçe: uç nokta testleri paylaşılan geliştirme veritabanına yazmamalı
(hem yavaş hem kirletici). Veritabanı davranışını `@pytest.mark.db`
işaretli testler ölçüyor.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from talimatname.api import bagimliliklar
from talimatname.api.routers import auth as auth_router
from talimatname.api.routers import dogrulama as dogrulama_router
from talimatname.domain.templates import Item
from talimatname.settings import get_settings


def _temizle() -> None:
    """Ayar bağını ve süreç başına tek örnekleri bırakır.

    Hız sayaçları modül düzeyinde, yani süreç ömrü boyunca yaşıyor:
    sınırı dolduran bir test, sıradakine 429 miras bırakırdı.
    """
    get_settings.cache_clear()
    bagimliliklar._ayarlar = None
    bagimliliklar.sifirla()
    auth_router.hiz_siniri.sifirla()
    dogrulama_router.hiz_siniri.sifirla()


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
    # Aynı şubede ikinci personel: çalıştırma kilidi iki kişi ister.
    "staff2": "+905321110006",  # Kadıköy
    "auditor": "+905321110009",  # Anadolu bölgesi denetçisi
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


def madde_degeri(madde: Item, durum: str) -> object:
    """Maddeyi istenen sonuca götüren değer (alan nesnesinden)."""
    return _deger(
        madde.type,
        madde.min_value,
        madde.max_value,
        [(s.label, s.passing) for s in madde.options],
        durum,
        madde.title,
    )


def json_madde_degeri(madde: dict[str, Any], durum: str) -> object:
    """Aynı değer, uç nokta cevabından.

    Uçtan uca testler maddeyi JSON olarak görüyor; değeri elle
    uydurmasınlar diye aynı çekirdek.
    """
    return _deger(
        madde["type"],
        madde.get("min_value"),
        madde.get("max_value"),
        [(o["label"], o.get("passing", True)) for o in madde.get("options", [])],
        durum,
        madde.get("title", ""),
    )


def _deger(
    tur: str,
    alt: float | None,
    ust: float | None,
    secenekler: list[tuple[str, bool]],
    durum: str,
    baslik: str,
) -> object:
    """Sonucu artık sunucu hesaplıyor (BR-06).

    Ölçüm maddesine "geçti" demek yetmiyor: aralığın içinden bir sayı,
    seçim maddesine de geçer bir seçenek gerekiyor. Testler bu değeri
    tek tek uydurursa aralık değiştiğinde sessizce bayatlar.
    """
    if durum in ("not_done", "not_applicable"):
        return None
    if tur in ("temperature", "number"):
        if alt is None or ust is None:
            return 0
        if durum == "failed":
            return ust + 1
        orta = (alt + ust) / 2
        return int(orta) if float(orta).is_integer() else orta
    if tur == "choice":
        istenen = durum == "passed"
        etiket = next((e for e, gecer in secenekler if gecer is istenen), None)
        assert etiket is not None, f"Şablonda '{durum}' veren seçenek yok: {baslik}"
        return etiket
    if tur == "text":
        return "Kontrol edildi"
    return None
