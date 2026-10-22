"""Şablon, sürüm ve yayın doğrulaması testleri (ST-014, ST-017; TC-018, TC-021, TC-022)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from talimatname.api.app import create_app
from talimatname.domain.templates import (
    ChoiceOption,
    Item,
    Section,
    TemplateVersion,
)
from talimatname.infra.memory import MemoryTemplateRepository, sabit_id
from talimatname.services.templates import (
    PublishRejected,
    TemplateService,
    VersionNotDraft,
    VersionNotFound,
)
from talimatname.settings import Settings

KAPANIS = sabit_id("sablon:kapanis")
ACILIS_TASLAK = sabit_id("surum:acilis:1")


def _servis(simdi: datetime | None = None) -> TemplateService:
    an = simdi or datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
    return TemplateService(MemoryTemplateRepository(), now=lambda: an)


def _madde(tur: str = "confirm", **ek: object) -> Item:
    alanlar: dict[str, object] = {
        "id": uuid4(),
        "order": 1,
        "type": tur,
        "title": "Test maddesi",
    }
    alanlar.update(ek)
    return Item(**alanlar)  # type: ignore[arg-type]


def _bolum(*maddeler: Item, baslik: str = "Bölüm") -> Section:
    return Section(id=uuid4(), order=1, title=baslik, items=maddeler)


# --- alan: yayın doğrulaması ------------------------------------------


def test_tc022_bos_sablon_yayinlanamaz() -> None:
    surum = TemplateVersion(id=uuid4(), template_id=uuid4(), version_no=1)
    assert [s.message for s in surum.publish_issues()] == ["En az bir bölüm olmalı"]


def test_tc022_bos_bolum_bildirilir() -> None:
    surum = TemplateVersion(
        id=uuid4(),
        template_id=uuid4(),
        version_no=1,
        sections=(Section(id=uuid4(), order=1, title="Mutfak"),),
    )
    mesajlar = [s.message for s in surum.publish_issues()]
    assert "'Mutfak' bölümü boş" in mesajlar


def test_tc022_tum_sorunlar_birden_doner() -> None:
    """FR-0312: kullanıcı sorunları tek tek keşfetmez, liste olarak görür."""
    surum = TemplateVersion(
        id=uuid4(),
        template_id=uuid4(),
        version_no=1,
        sections=(
            _bolum(
                _madde("choice", title="Seçeneksiz"),
                _madde("temperature", title="Aralıksız"),
                _madde("confirm", title="Kritik ama zorunlu değil", critical=True, required=False),
            ),
        ),
    )
    mesajlar = [s.message for s in surum.publish_issues()]
    assert len(mesajlar) == 3
    assert "en az iki seçenek" in mesajlar[0]
    assert "Alt ve üst sınır" in mesajlar[1]
    assert "Kritik madde zorunlu" in mesajlar[2]


def test_secenekler_hepsi_gecmez_olamaz() -> None:
    surum = TemplateVersion(
        id=uuid4(),
        template_id=uuid4(),
        version_no=1,
        sections=(
            _bolum(
                _madde(
                    "choice",
                    options=(ChoiceOption("Hayır", False), ChoiceOption("Hiç", False)),
                )
            ),
        ),
    )
    assert "geçer" in surum.publish_issues()[0].message


def test_talimat_satiri_kritik_olamaz() -> None:
    surum = TemplateVersion(
        id=uuid4(),
        template_id=uuid4(),
        version_no=1,
        sections=(_bolum(_madde("instruction", critical=True)),),
    )
    assert "Talimat satırı" in surum.publish_issues()[0].message


def test_yalnizca_talimattan_olusan_sablon_yayinlanamaz() -> None:
    surum = TemplateVersion(
        id=uuid4(),
        template_id=uuid4(),
        version_no=1,
        sections=(_bolum(_madde("instruction")),),
    )
    assert "cevaplanabilir madde" in surum.publish_issues()[0].message


def test_ters_aralik_reddedilir() -> None:
    surum = TemplateVersion(
        id=uuid4(),
        template_id=uuid4(),
        version_no=1,
        sections=(_bolum(_madde("temperature", min_value=10, max_value=4)),),
    )
    assert "küçük olmalı" in surum.publish_issues()[0].message


def test_puanlanan_madde_sayisi_talimati_saymaz() -> None:
    surum = TemplateVersion(
        id=uuid4(),
        template_id=uuid4(),
        version_no=1,
        sections=(_bolum(_madde("confirm"), _madde("instruction"), _madde("photo")),),
    )
    assert surum.scored_item_count == 2


# --- servis ------------------------------------------------------------


def test_tc021_yayinlanan_surum_degismez() -> None:
    servis = _servis()
    yayinda = servis.published(KAPANIS)
    assert yayinda is not None

    with pytest.raises(VersionNotDraft):
        servis.save_draft(yayinda.id, ())


def test_yeni_taslak_yayindan_turetilir() -> None:
    servis = _servis()
    yayinda = servis.published(KAPANIS)
    assert yayinda is not None

    taslak = servis.new_draft(KAPANIS)

    assert taslak.version_no == yayinda.version_no + 1
    assert taslak.status == "draft"
    assert taslak.sections == yayinda.sections  # içerik kopyalandı
    assert servis.published(KAPANIS) == yayinda  # yayın el değmeden duruyor


def test_acik_taslak_varken_ikinci_taslak_uretilmez() -> None:
    servis = _servis()
    ilk = servis.new_draft(KAPANIS)
    ikinci = servis.new_draft(KAPANIS)
    assert ilk.id == ikinci.id


def test_tc021_yayin_oncekini_arsivler() -> None:
    an = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)
    servis = _servis(an)
    eski = servis.published(KAPANIS)
    assert eski is not None
    taslak = servis.new_draft(KAPANIS)

    yeni = servis.publish(taslak.id)

    assert yeni.status == "published"
    assert yeni.published_at == an
    assert servis.version(eski.id).status == "archived"
    assert servis.published(KAPANIS) == yeni


def test_dogrulanamayan_taslak_yayinlanmaz() -> None:
    servis = _servis()
    servis.save_draft(ACILIS_TASLAK, (_bolum(_madde("choice", title="Seçeneksiz")),))

    with pytest.raises(PublishRejected) as hata:
        servis.publish(ACILIS_TASLAK)

    assert hata.value.extra["issues"][0]["message"].startswith("Çoktan seçmeli")


def test_olmayan_surum() -> None:
    with pytest.raises(VersionNotFound):
        _servis().version(uuid4())


# --- uç noktalar -------------------------------------------------------


@pytest.fixture
def istemci() -> TestClient:
    return TestClient(create_app(Settings()))


def test_uc_nokta_sablon_listesi(istemci: TestClient) -> None:
    yanit = istemci.get("/api/v1/templates")
    assert yanit.status_code == 200
    adlar = [s["name"] for s in yanit.json()]
    assert adlar == sorted(adlar, key=str.casefold)
    kapanis = next(s for s in yanit.json() if s["name"].startswith("Kapanış"))
    assert kapanis["versions"][0]["status"] == "published"
    assert kapanis["versions"][0]["critical_item_count"] == 2


def test_tc018_surum_detayinda_madde_turleri_etiketli(istemci: TestClient) -> None:
    kapanis = next(
        s for s in istemci.get("/api/v1/templates").json() if s["name"].startswith("Kapanış")
    )
    detay = istemci.get(f"/api/v1/template-versions/{kapanis['versions'][0]['id']}").json()

    turler = {m["type_label"] for b in detay["sections"] for m in b["items"]}
    assert {"Talimat", "Onay", "Fotoğraf", "Sıcaklık", "Çoktan seçmeli", "Metin"} <= turler
    talimat = next(m for b in detay["sections"] for m in b["items"] if m["type"] == "instruction")
    assert talimat["scored"] is False


def test_uc_nokta_sablon_olusturma_taslak_acar(istemci: TestClient) -> None:
    yanit = istemci.post("/api/v1/templates", json={"name": "Teslimat kabul"})
    assert yanit.status_code == 201
    govde = yanit.json()
    assert govde["status"] == "draft"
    assert govde["version_no"] == 1
    assert govde["publish_issues"][0]["message"] == "En az bir bölüm olmalı"


def test_uc_nokta_taslak_kaydedilir_ve_yayinlanir(istemci: TestClient) -> None:
    olustur = istemci.post("/api/v1/templates", json={"name": "Haftalık derin temizlik"}).json()

    kaydet = istemci.put(
        f"/api/v1/template-versions/{olustur['id']}",
        json={
            "sections": [
                {
                    "title": "Davlumbaz",
                    "items": [
                        {"type": "photo", "title": "Filtre temizlendi", "photo_required": True},
                        {
                            "type": "choice",
                            "title": "Yağ toplandı",
                            "options": [
                                {"label": "Evet", "passing": True},
                                {"label": "Hayır", "passing": False},
                            ],
                        },
                    ],
                }
            ],
            "camera_only": True,
        },
    )
    assert kaydet.status_code == 200
    assert kaydet.json()["publish_issues"] == []
    assert kaydet.json()["scored_item_count"] == 2

    yayin = istemci.post(f"/api/v1/template-versions/{olustur['id']}/publish")
    assert yayin.status_code == 200
    assert yayin.json()["status"] == "published"


def test_uc_nokta_yayin_reddi_tum_sorunlari_doner(istemci: TestClient) -> None:
    olustur = istemci.post("/api/v1/templates", json={"name": "Bozuk şablon"}).json()
    istemci.put(
        f"/api/v1/template-versions/{olustur['id']}",
        json={
            "sections": [
                {
                    "title": "Bölüm",
                    "items": [
                        {"type": "choice", "title": "Seçeneksiz"},
                        {"type": "number", "title": "Aralıksız"},
                    ],
                }
            ],
            "camera_only": True,
        },
    )

    yanit = istemci.post(f"/api/v1/template-versions/{olustur['id']}/publish")

    assert yanit.status_code == 422
    govde = yanit.json()
    assert govde["type"] == "urn:talimatname:yayin-dogrulanamadi"
    assert len(govde["issues"]) == 2
