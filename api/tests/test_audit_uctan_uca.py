"""Olay günlüğünün uçtan uca hâli (FR-1301, FR-1218; TC-100).

Alan testleri zinciri hesaplıyor (`test_audit`); burada sınanan şey
**günlüğün gerçekten dolduğu**: oturum açılınca, liste gönderilince,
rapor dökülünce kayıt düşüyor mu, "nereden" bilgisi geliyor mu, kâğıt
üstündeki kod zincire bağlanıyor mu.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from conftest import oturum_ac
from talimatname.api import bagimliliklar
from talimatname.api.app import create_app
from talimatname.settings import Settings

YONETICI = "+905321110001"


@pytest.fixture
def istemci(tmp_path: Path) -> TestClient:
    return TestClient(create_app(Settings(evidence_dir=str(tmp_path))))


def _iz() -> list[tuple[str, str | None]]:
    servis = bagimliliklar.izi_servisi()
    rapor = servis.verify(limit=1000)
    assert rapor.intact, f"zincir kırık: {rapor.breaks}"
    return [(o.event_type, o.ip) for o in servis._repo.events(limit=1000)]


# --- oturum (FR-1301) --------------------------------------------------


def test_oturum_acilisi_gunluge_dusuyor(istemci: TestClient) -> None:
    kod = istemci.post("/api/v1/auth/request-code", json={"phone": YONETICI}).json()["dev_code"]

    istemci.post("/api/v1/auth/verify", json={"phone": YONETICI, "code": kod})

    turler = [t for t, _ in _iz()]
    assert "oturum.acildi" in turler


def test_reddedilen_deneme_de_gunluge_dusuyor(istemci: TestClient) -> None:
    """ "Kim girmeye çalıştı" sorusu denetimde en az "kim girdi" kadar sorulur."""
    istemci.post("/api/v1/auth/request-code", json={"phone": YONETICI})

    yanit = istemci.post("/api/v1/auth/verify", json={"phone": YONETICI, "code": "000000"})

    assert yanit.status_code == 403
    turler = [t for t, _ in _iz()]
    assert "oturum.reddedildi" in turler


def test_istek_baglami_olaya_giriyor(istemci: TestClient) -> None:
    """IP ve cihaz yalnızca HTTP katmanında biliniyor; olaya oradan geçiyor."""
    kod = istemci.post("/api/v1/auth/request-code", json={"phone": YONETICI}).json()["dev_code"]

    istemci.post(
        "/api/v1/auth/verify",
        json={"phone": YONETICI, "code": kod},
        headers={"X-Forwarded-For": "198.51.100.7, 10.0.0.1", "User-Agent": "Talimatname/1.0"},
    )

    servis = bagimliliklar.izi_servisi()
    olay = next(o for o in servis._repo.events(limit=100) if o.event_type == "oturum.acildi")
    assert olay.ip == "198.51.100.7"  # vekil zincirinin başı
    assert olay.device == "Talimatname/1.0"
    assert olay.actor_id is not None


def test_telefon_numarasi_gunluge_yazilmiyor(istemci: TestClient) -> None:
    """Kişisel veri günlükte durmaz (BR-21): kayıt kimlikle bağlanıyor."""
    kod = istemci.post("/api/v1/auth/request-code", json={"phone": YONETICI}).json()["dev_code"]
    istemci.post("/api/v1/auth/verify", json={"phone": YONETICI, "code": kod})

    servis = bagimliliklar.izi_servisi()
    metin = str([(o.before, o.after) for o in servis._repo.events(limit=100)])

    assert "905321110001" not in metin


# --- rapor kodu (FR-1218) ----------------------------------------------


def _pdf_metni(baytlar: bytes) -> str:
    return "\n".join(s.extract_text() or "" for s in PdfReader(io.BytesIO(baytlar)).pages)


def test_rapor_kodu_zincirdeki_kayda_bagli(istemci: TestClient) -> None:
    """Kâğıttaki kod, raporun üretildiği olayın zincir özeti.

    Doğrulama sayfası (v1.x) koda göre kaydı bulacak; şimdiden bağ
    kurulmazsa o sayfa yazılırken geçmiş raporlar bağsız kalırdı.
    """
    oturum_ac(istemci)
    bugun = datetime.now(UTC).date()

    yanit = istemci.get(
        "/api/v1/reports/monthly.pdf", params={"year": bugun.year, "month": bugun.month}
    )

    assert yanit.status_code == 200
    servis = bagimliliklar.izi_servisi()
    olay = next(o for o in servis._repo.events(limit=200) if o.event_type == "rapor.uretildi")
    ozet = olay.hash[:12].upper()
    beklenen = f"{ozet[:4]}-{ozet[4:8]}-{ozet[8:]}"

    metin = _pdf_metni(yanit.content)
    assert f"Belge kodu: {beklenen}" in metin
    assert "olay günlüğündeki kaydının özetidir" in metin
    assert olay.after["tur"] == "aylik-ozet"
    assert olay.after["icerik"]  # hangi verinin döküldüğü de kayıtta


def test_gunluk_yoksa_kagit_kodun_bagsiz_oldugunu_yaziyor(
    istemci: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bağlıymış gibi yazmak, olmayan bir güvence vermek olurdu."""
    oturum_ac(istemci)
    servis = bagimliliklar.izi_servisi()
    monkeypatch.setattr(servis, "record", lambda *a, **k: None)
    bugun = datetime.now(UTC).date()

    yanit = istemci.get(
        "/api/v1/reports/monthly.pdf", params={"year": bugun.year, "month": bugun.month}
    )

    metin = _pdf_metni(yanit.content)
    assert "zincire bağlı değil" in metin


# --- ekle-yalnızlık (TC-100) -------------------------------------------


def test_gunlugu_degistiren_uc_nokta_yok(istemci: TestClient) -> None:
    """Olay günlüğünü yazan/silen bir uç nokta olmamalı.

    Sözleşmeyi (OpenAPI) tarıyoruz: ileride biri "düzeltme" uç noktası
    eklerse bu test kırmızı yanar ve karar bilinçli alınır.
    """
    yollar = istemci.get("/api/v1/openapi.json").json()["paths"]

    izle_ilgili = {
        yol: list(islemler)
        for yol, islemler in yollar.items()
        if "audit" in yol or "olay" in yol or "izi" in yol
    }
    yazanlar = {
        yol: [m for m in islemler if m in {"post", "put", "patch", "delete"}]
        for yol, islemler in izle_ilgili.items()
    }

    assert not any(yazanlar.values()), yazanlar


def test_zamanlayici_turu_istegin_ipsini_tasimaz(istemci: TestClient) -> None:
    """Tur arka plan işi: tetikleyen isteğin IP'si olaya geçmemeli.

    Geçseydi, süpürülen bir kanıdın yanında o anda panele bakan
    kullanıcının IP'si yazardı: "bu kullanıcı sildi" gibi okunurdu.
    """
    oturum_ac(istemci)

    istemci.post(
        "/api/v1/scheduler/tick",
        headers={"X-Forwarded-For": "198.51.100.9", "User-Agent": "Panel/1.0"},
    )

    servis = bagimliliklar.izi_servisi()
    tur_olaylari = [
        o
        for o in servis._repo.events(limit=200)
        if o.event_type in {"kanit.supuruldu", "calistirma.kacirildi"}
    ]
    assert all(o.ip is None and o.device is None for o in tur_olaylari)
