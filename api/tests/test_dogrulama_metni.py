"""Şema doğrulama sebeplerinin Türkçeliği (bağımsız test turu O-2).

İstemci `errors[].sebep`i doğrudan ekrana basıyor (`Durum.tsx`), o yüzden
bu metinler kullanıcı metnidir: İngilizce sızmamalı.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import oturum_ac
from talimatname.api.app import create_app
from talimatname.api.dogrulama_metni import turkce
from talimatname.settings import Settings

#: İngilizce sızıntısını yakalayan kaba süzgeç.
INGILIZCE = re.compile(
    r"\b(input|should|should be|field|required|valid|value|string|integer|"
    r"invalid|expected|missing|type|character|found)\b",
    re.IGNORECASE,
)


@pytest.mark.parametrize(
    ("hata", "beklenen"),
    [
        ({"type": "missing"}, "Bu alan zorunlu"),
        ({"type": "uuid_parsing"}, "Geçerli bir kimlik (UUID) olmalı"),
        ({"type": "int_parsing"}, "Tam sayı olmalı"),
        ({"type": "extra_forbidden"}, "Bu alan beklenmiyor"),
        ({"type": "greater_than_equal", "ctx": {"ge": 5}}, "En az 5 olmalı"),
        ({"type": "string_too_long", "ctx": {"max_length": 80}}, "En fazla 80 karakter olabilir"),
        ({"type": "bilinmeyen_tip"}, "Değer geçerli değil"),
        # Bağlam gelmezse yer tutuculu kalıp sızmamalı.
        ({"type": "greater_than_equal"}, "Değer geçerli değil"),
    ],
)
def test_tipler_turkceye_cevriliyor(hata: dict[str, object], beklenen: str) -> None:
    assert turkce(hata) == beklenen


def test_secenekli_hata_secenekleri_yaziyor() -> None:
    sebep = turkce({"type": "literal_error", "ctx": {"expected": "'passed', 'failed' or 'done'"}})

    assert sebep == "Şunlardan biri olmalı: 'passed', 'failed' ya da 'done'"
    assert " or " not in sebep


def test_alan_dogrulayicisinin_kendi_cumlesi_korunuyor() -> None:
    """`value_error` bizim yazdığımız Türkçe cümle: çevrilecek bir şey yok."""
    sebep = turkce({"type": "value_error", "ctx": {"error": "pencere ve tolerans toplamı aşıldı"}})

    assert sebep == "pencere ve tolerans toplamı aşıldı"


@pytest.fixture
def istemci(tmp_path: Path) -> TestClient:
    return oturum_ac(TestClient(create_app(Settings(evidence_dir=str(tmp_path)))))


def test_uc_nokta_gecersiz_govdede_turkce_sebep_donuyor(istemci: TestClient) -> None:
    """Gerçek istek: Pydantic'in İngilizce `msg`i kullanıcıya ulaşmamalı."""
    kosu = istemci.get("/api/v1/runs").json()[0]
    yanit = istemci.put(
        f"/api/v1/runs/{kosu['id']}/answers/11111111-2222-3333-4444-555555555555",
        json={"item_id": "bu-bir-uuid-degil", "state": "olmayan-durum"},
    )

    assert yanit.status_code == 422, yanit.text
    govde = yanit.json()
    assert govde["title"] == "İstek doğrulanamadı"
    sebepler = [h["sebep"] for h in govde["errors"]]
    assert sebepler, "alan sebebi dönmedi"
    for sebep in sebepler:
        assert not INGILIZCE.search(sebep), f"İngilizce sızdı: {sebep}"


def test_alan_hatasi_hangi_alan_oldugunu_soyluyor(istemci: TestClient) -> None:
    """D-4: form hatayı alanın yanına yazabilsin diye `errors` dolu gelmeli."""
    mevcut = next(s for d in istemci.get("/api/v1/branches").json() for s in d["branches"])

    yanit = istemci.post(
        "/api/v1/branches",
        json={"code": mevcut["code"], "name": "Çakışma", "timezone": "Europe/Istanbul"},
    )

    assert yanit.status_code == 409, yanit.text
    govde = yanit.json()
    assert govde["title"] == "Bu şube kodu zaten var"
    assert govde["errors"] == [{"alan": "code", "sebep": "Bu şube kodu zaten var"}]


def test_alani_olmayan_kural_hatasi_errors_tasimiyor(istemci: TestClient) -> None:
    """Her kural hatası bir alana ait değil: uydurma alan adı üretilmemeli."""
    kosu = istemci.get("/api/v1/runs").json()[0]

    yanit = istemci.post(f"/api/v1/runs/{kosu['id']}/cancel", json={"reason": ""})

    assert yanit.status_code in (409, 422), yanit.text
    assert "code" not in str(yanit.json().get("errors", ""))
