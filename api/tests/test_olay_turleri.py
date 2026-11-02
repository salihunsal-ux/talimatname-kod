"""Genişletilen olay türleri (FR-0913, FR-0915, FR-1301).

Günlüğün değeri kapsamıyla ölçülüyor: eskalasyon yürüdüyse, personel
rolü değiştiyse, plan gevşetildiyse veya şablon yayınlandıysa kayıt
düşmeli. Bir de düşmemesi gereken yer var: **aynı adım her turda
yeniden yazılmamalı** — zamanlayıcı dakikada bir koşuyor.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import talimatname
from conftest import TELEFON, oturum_ac
from talimatname.api import bagimliliklar
from talimatname.api.app import create_app
from talimatname.domain.audit import EVENT_TYPES
from talimatname.domain.users import RoleAssignment, User
from talimatname.settings import Settings


def _olaylar(tur: str | None = None) -> list[object]:
    servis = bagimliliklar.izi_servisi()
    hepsi = servis._repo.events(limit=2000)
    return [o for o in hepsi if tur is None or o.event_type == tur]


@pytest.fixture
def istemci(tmp_path: Path) -> TestClient:
    return TestClient(create_app(Settings(evidence_dir=str(tmp_path))))


# --- sözleşme -----------------------------------------------------------


def test_her_olay_turunun_yazan_bir_yeri_var() -> None:
    """Listede durup hiç yazılmayan tür, tutulmayan bir sözdür.

    Günlüğe bakan biri "eskalasyonlar burada" diye okuyup boş
    bulursa, olmadığını değil kaydedilmediğini anlayamaz. Bu test
    tür listesiyle kodu birbirine bağlıyor.
    """
    kok = Path(talimatname.__file__).parent
    kaynak = "\n".join(
        yol.read_text(encoding="utf-8")
        for yol in kok.rglob("*.py")
        if not (yol.name == "audit.py" and yol.parent.name == "domain")
    )

    yazilmayan = [tur for tur in EVENT_TYPES if f'"{tur}"' not in kaynak]

    assert not yazilmayan, f"yazan yeri olmayan tür: {yazilmayan}"


# --- kaçırma ------------------------------------------------------------


def test_kacirma_bir_kez_yaziliyor(istemci: TestClient) -> None:
    """Durum bir kez değişiyor, kayıt da bir kez düşüyor.

    Her turda yazsaydık zincir, hiçbir şey olmadığı hâlde dakikada
    bir büyürdü.
    """
    oturum_ac(istemci)
    istemci.post("/api/v1/scheduler/tick")
    once = len(_olaylar("calistirma.kacirildi"))

    istemci.post("/api/v1/scheduler/tick")

    assert once > 0, "tohumda kaçırılmış çalıştırma bekleniyordu"
    assert len(_olaylar("calistirma.kacirildi")) == once
    olay = _olaylar("calistirma.kacirildi")[0]
    assert olay.before == {"durum": "scheduled"} or olay.before == {  # type: ignore[attr-defined]
        "durum": "in_progress"
    }
    assert olay.after["durum"] == "missed"  # type: ignore[attr-defined,index]


def test_kacirma_olayinin_aktoru_yok(istemci: TestClient) -> None:
    """Kaçırmayı kimse yapmadı: zaman yaptı. Aktör uydurmuyoruz."""
    oturum_ac(istemci)
    istemci.post("/api/v1/scheduler/tick")

    olay = _olaylar("calistirma.kacirildi")[0]

    assert olay.actor_id is None  # type: ignore[attr-defined]
    assert olay.ip is None  # type: ignore[attr-defined]


# --- personel ------------------------------------------------------------


def test_kod_istegi_gunluge_yaziliyor(istemci: TestClient) -> None:
    """Oturumsuz uç nokta iz bırakmalı (FR-1301).

    Kod isteği kimlik doğrulamanın ilk adımı; kayıtlı numaraya 200,
    kayıtsıza 404 döndüğü için **numara sorgusu** olarak da
    kullanılabiliyor. Sınırsız ve izsizken bir zincirin personel
    listesi fark edilmeden çıkarılabiliyordu.
    """
    once = len(_olaylar("oturum.kod_istendi"))

    bilinen = istemci.post("/api/v1/auth/request-code", json={"phone": TELEFON["admin"]})
    bilinmeyen = istemci.post("/api/v1/auth/request-code", json={"phone": "+905329999999"})

    assert bilinen.status_code == 200
    assert bilinmeyen.status_code == 404

    olaylar = _olaylar("oturum.kod_istendi")[once:]
    assert len(olaylar) == 2, "iki istek de yazılmalı"

    gonderildi, yoklama = olaylar
    assert gonderildi.object_id is not None  # type: ignore[attr-defined]
    assert yoklama.object_id is None, "bilinmeyen numara bir kullanıcıya bağlanamaz"  # type: ignore[attr-defined]
    assert yoklama.after == {"sonuc": "bilinmeyen"}  # type: ignore[attr-defined]


def test_kod_istegi_telefonu_gunluge_yazmiyor(istemci: TestClient) -> None:
    """BR-21: yoklanan numaralar ürünün içinde birikmemeli."""
    numara = "+905329998811"

    istemci.post("/api/v1/auth/request-code", json={"phone": numara})

    metin = str([(o.after, o.object_type) for o in _olaylar("oturum.kod_istendi")])  # type: ignore[attr-defined]
    assert numara not in metin
    assert "905329998811" not in metin


def test_kod_istegi_hiz_siniri(istemci: TestClient) -> None:
    """Sınırsız uç nokta, numara sorgusunu bedava hâle getiriyordu."""
    from talimatname.api.routers import auth as auth_router

    kodlar = [
        istemci.post(
            "/api/v1/auth/request-code", json={"phone": f"+90532000{sira:04d}"}
        ).status_code
        for sira in range(auth_router.KOD_ISTEK_SINIRI + 2)
    ]

    assert kodlar[0] == 404, "bilinmeyen numara: sınıra kadar normal yanıt"
    assert kodlar[-1] == 429, f"sınır sonrası reddedilmeli, görülen: {kodlar[-3:]}"


def test_personel_olaylari_ad_ve_telefon_tasimiyor(istemci: TestClient) -> None:
    """BR-21: günlük kişiyi kimliğiyle tutar, adıyla değil.

    Maskelenen bir kullanıcının günlüğü de maskelenmiş kalmalı;
    adı yazarsak maskeleme eksik kalır.
    """
    yonetici = oturum_ac(istemci)
    sube = bagimliliklar._org_deposu().branches()[0]

    yanit = yonetici.post(
        "/api/v1/users",
        json={
            "full_name": "Deneme Personel",
            "phone": "+905329998877",
            "assignments": [{"role": "staff", "scope_id": str(sube.id)}],
        },
    )

    assert yanit.status_code in (200, 201), yanit.text
    davet = _olaylar("personel.davet")
    assert len(davet) == 1
    assert davet[0].object_id is not None  # type: ignore[attr-defined]
    metin = str(davet[0].after)  # type: ignore[attr-defined]
    assert "Deneme Personel" not in metin
    assert "905329998877" not in metin
    assert davet[0].after["roller"] == "staff"  # type: ignore[attr-defined,index]


def test_rol_degisikligi_once_sonrayla_yaziliyor() -> None:
    """ "Bu kişiye yöneticiliği kim verdi" denetimin sorusu."""
    create_app(Settings())
    servis = bagimliliklar.kullanici_servisi()
    kisi = servis.invite(
        User(
            id=uuid4(),
            full_name="Deneme Kisi",
            phone="+905329990011",
            assignments=(RoleAssignment(role="admin"),),
        )
    )

    sube = bagimliliklar._org_deposu().branches()[0]
    servis.update(kisi.id, assignments=(RoleAssignment(role="staff", scope_id=sube.id),))

    olay = _olaylar("personel.guncellendi")[-1]
    assert olay.before["roller"] == "admin"  # type: ignore[attr-defined,index]
    assert olay.after["roller"] == "staff"  # type: ignore[attr-defined,index]
    assert olay.after["degisen"] == "roller"  # type: ignore[attr-defined,index]


def test_ad_degisikliginde_yeni_ad_gunluge_girmiyor() -> None:
    """Özet **yalnızca değişeni** taşıyor ve değeri değil adını yazıyor.

    Rol değişmediyse "roller" alanı hiç görünmüyor: değişmeyeni yazmak
    günlüğü şişirir ve okuyanı yorar (`summary_of`).
    """
    create_app(Settings())
    servis = bagimliliklar.kullanici_servisi()
    kisi = servis.invite(
        User(
            id=uuid4(),
            full_name="Deneme Kisi",
            phone="+905329990033",
            assignments=(RoleAssignment(role="admin"),),
        )
    )

    servis.update(kisi.id, full_name="Deneme Kisi 2")

    olay = _olaylar("personel.guncellendi")[-1]
    assert olay.after["degisen"] == "ad"  # type: ignore[attr-defined,index]
    assert "roller" not in olay.after  # type: ignore[attr-defined,operator]
    assert "Deneme Kisi 2" not in str(olay.after)  # type: ignore[attr-defined]


def test_maskeleme_ayri_tur() -> None:
    """KVKK silme talebi sıradan bir güncelleme değil (FR-1310)."""
    create_app(Settings())
    servis = bagimliliklar.kullanici_servisi()
    kisi = servis.invite(
        User(
            id=uuid4(),
            full_name="Maskelenecek Kisi",
            phone="+905329990022",
            assignments=(RoleAssignment(role="admin"),),
        )
    )

    servis.mask(kisi.id)

    olaylar = _olaylar("personel.maskelendi")
    assert [o.object_id for o in olaylar] == [kisi.id]  # type: ignore[attr-defined]
    assert olaylar[0].after["durum"] == "masked"  # type: ignore[attr-defined,index]
    assert "Maskelenecek" not in str(olaylar[0].after)  # type: ignore[attr-defined]


# --- plan ve şablon ------------------------------------------------------


def test_plan_kurulumu_ve_degisikligi_yaziliyor() -> None:
    """Kontrolün ne zaman gevşetildiği plan kaydından okunamaz: sürümü yok."""
    create_app(Settings())
    servis = bagimliliklar.plan_servisi()
    plan = servis.list_plans()[0]

    servis.update(plan.id, active=False)

    olay = _olaylar("plan.guncellendi")[-1]
    assert olay.before["etkin"] == "evet"  # type: ignore[attr-defined,index]
    assert olay.after["etkin"] == "hayır"  # type: ignore[attr-defined,index]
    # Değişmeyen alanlar özete girmiyor: günlük "ne değişti" sorusuyla başlar.
    assert "ad" not in olay.after  # type: ignore[attr-defined,operator]


def test_sablon_yayini_yaziliyor() -> None:
    """Denetimde "o gün hangi liste yürürlükteydi" sorusunun izi.

    Tohumdaki yayınlı şablondan yeni taslak türetip yayınlıyoruz:
    maddeleri olduğu gibi devralıyor, yani yayın kontrollerinden
    geçiyor ve test şablon kurmakla uğraşmıyor.
    """
    create_app(Settings())
    servis = bagimliliklar.sablon_servisi()
    sablon, _ = servis.list_templates()[0]
    taslak = servis.new_draft(sablon.id)

    servis.publish(taslak.id)

    olay = _olaylar("sablon.yayinlandi")[-1]
    assert olay.object_id == sablon.id  # type: ignore[attr-defined]
    assert olay.after["ad"] == sablon.name  # type: ignore[attr-defined,index]
    assert int(olay.after["madde"]) > 0  # type: ignore[attr-defined,index]
    assert olay.after["surum"] == str(taslak.version_no)  # type: ignore[attr-defined,index]


# --- zincir --------------------------------------------------------------


def test_yeni_turler_zinciri_kirmiyor(istemci: TestClient) -> None:
    """Hepsi birlikte: zincir bütün kalmalı."""
    yonetici = oturum_ac(istemci)
    istemci.post("/api/v1/scheduler/tick")
    sube = bagimliliklar._org_deposu().branches()[0]
    yonetici.post(
        "/api/v1/users",
        json={
            "full_name": "Zincir Deneme",
            "phone": "+905329997755",
            "assignments": [{"role": "staff", "scope_id": str(sube.id)}],
        },
    )
    istemci.post("/api/v1/scheduler/tick")

    rapor = bagimliliklar.izi_servisi().verify(limit=5000)

    assert rapor.intact, f"zincir kırık: {rapor.breaks}"
    turler = {o.event_type for o in _olaylar()}  # type: ignore[attr-defined]
    assert {"calistirma.kacirildi", "personel.davet"} <= turler


def test_gunluk_yazilamasa_bile_is_surer(
    istemci: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Denetim izi değerli ama ürünün kendisi değil (services/audit)."""
    yonetici = oturum_ac(istemci)
    servis = bagimliliklar.izi_servisi()
    monkeypatch.setattr(servis, "record", lambda *a, **k: None)
    sube = bagimliliklar._org_deposu().branches()[0]

    yanit = yonetici.post(
        "/api/v1/users",
        json={
            "full_name": "Gunluksuz Kisi",
            "phone": "+905329996644",
            "assignments": [{"role": "staff", "scope_id": str(sube.id)}],
        },
    )

    assert yanit.status_code in (200, 201), yanit.text


def test_tur_etiketleri_turkce_ve_tekil() -> None:
    """Etiket ekranda görünüyor: boş ya da yinelenen etiket okunamaz."""
    assert all(etiket.strip() for etiket in EVENT_TYPES.values())
    assert len(set(EVENT_TYPES.values())) == len(EVENT_TYPES)
