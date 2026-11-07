"""Zincir kökünün dış çıpalanması (ST-103; FR-1302).

Zincirin tek açığı şuydu: veritabanına yazabilen biri tarihi **baştan**
hesaplarsa fark edilmez. Çıpa bunu kapatıyor ve testlerin asıl işi de
bu: damganın gerçekten alındığını, saklandığını ve **sonradan yazılan
bir geçmişin** çıpayla tutmadığını göstermek.

Damgalar sahte değil: test içinde üretilen bir sertifikayla imzalanmış
gerçek RFC 3161 belirteçleri (`sahte_tsa`). "Bayt geldi" demek,
damganın çözülüp imzasının tuttuğunu göstermez.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from conftest import oturum_ac
from sahte_tsa import SahteTsa
from talimatname.api import bagimliliklar
from talimatname.api.app import create_app
from talimatname.domain import chain_anchor
from talimatname.domain.audit import AuditEvent, sealed
from talimatname.domain.chain_anchor import ChainAnchor, due, local_day
from talimatname.domain.validation import ValidationError
from talimatname.infra.memory import MemoryAnchorRepository, MemoryAuditRepository
from talimatname.infra.tsa import Rfc3161Authority
from talimatname.services.anchors import AnchorService, Stamp, TimestampError
from talimatname.services.audit import tampered
from talimatname.settings import Settings

AN = datetime(2026, 11, 1, 6, 0, tzinfo=UTC)  # İstanbul'da 09:00
ISTANBUL = "Europe/Istanbul"


class SahteOtorite:
    """`TimestampAuthority` portunun test karşılığı: gerçek damga üretir."""

    def __init__(self, *, patlat: bool = False) -> None:
        self._tsa = SahteTsa()
        self._cozucu = Rfc3161Authority("http://kullanilmiyor")
        self.patlat = patlat
        self.sayac = 0

    def stamp(self, digest: bytes) -> Stamp:
        self.sayac += 1
        if self.patlat:
            raise TimestampError("Sunucuya ulaşılamadı")
        token = self._tsa.damga(digest, nonce=1, gen_time=AN)
        return Stamp(token=token, stamped_at=AN, tsa_name="Deneme TSA", serial="1")

    def covers(self, token: bytes, digest: bytes) -> bool:
        return self._cozucu.covers(token, digest)


def _dunya(
    *, otorite: SahteOtorite | None = None, an: datetime = AN
) -> tuple[MemoryAuditRepository, MemoryAnchorRepository, AnchorService]:
    gunluk = MemoryAuditRepository()
    cipalar = MemoryAnchorRepository()
    servis = AnchorService(
        cipalar,
        gunluk,
        otorite,
        timezone=lambda: ISTANBUL,
        now=lambda: an,
    )
    return gunluk, cipalar, servis


def _olay(gunluk: MemoryAuditRepository, sira: int = 1, **ek: object) -> AuditEvent:
    olay = sealed(
        AuditEvent(
            id=uuid4(),
            sequence=sira,
            event_type="oturum.acildi",
            at=AN,
            object_type="kullanici",
            **ek,  # type: ignore[arg-type]
        )
    )
    gunluk.append(olay)
    return olay


# --- alan katmanı -------------------------------------------------------


def test_cipa_saati_gecmisse_de_aliniyor() -> None:
    """Zamanlayıcı 04:00'te kapalıysa, açıldığı anda alınır.

    "Tam saatinde değilse hiç" demek, sunucunun bir saat kapalı
    kalmasını çıpasız bir güne çevirirdi.
    """
    gece = datetime(2026, 11, 1, 3, 30, tzinfo=ZoneInfo(ISTANBUL))
    sabah = datetime(2026, 11, 1, 9, 0, tzinfo=ZoneInfo(ISTANBUL))

    assert not due(gece, attempts_today=0, has_anchor_today=False)
    assert due(sabah, attempts_today=0, has_anchor_today=False)


def test_gunde_bir_cipa_ve_en_cok_uc_deneme() -> None:
    sabah = datetime(2026, 11, 1, 9, 0, tzinfo=ZoneInfo(ISTANBUL))

    assert not due(sabah, attempts_today=1, has_anchor_today=True)
    assert due(sabah, attempts_today=2, has_anchor_today=False)
    # Üçüncüden sonra ertesi gün: damga sunucusuna dakikada bir
    # yüklenen bir istemciye dönüşmemeli.
    assert not due(sabah, attempts_today=3, has_anchor_today=False)


def test_yerel_gun_utc_gununden_farkli_olabilir() -> None:
    """Çıpa bir **günün** çıpası ve gün yerel takvimde başlıyor."""
    gece_yarisi_sonrasi = datetime(2026, 11, 1, 22, 30, tzinfo=UTC)

    assert local_day(gece_yarisi_sonrasi, ISTANBUL).day == 2
    assert local_day(gece_yarisi_sonrasi, "UTC").day == 1


def test_damgasiz_basarili_cipa_kabul_edilmiyor() -> None:
    """Başarılı denip damgası olmayan kayıt, olmayan güvence demek."""
    with pytest.raises(ValidationError):
        ChainAnchor(
            id=uuid4(), created_at=AN, sequence=1, chain_hash="a" * 64, state="ok"
        ).validated()


# --- servis -------------------------------------------------------------


def test_cipa_zincirin_basini_damgaliyor() -> None:
    otorite = SahteOtorite()
    gunluk, _, servis = _dunya(otorite=otorite)
    _olay(gunluk, 1)
    bas = _olay(gunluk, 2)

    cipa = servis.anchor_now()

    assert cipa is not None
    assert (cipa.state, cipa.sequence, cipa.chain_hash) == ("ok", 2, bas.hash)
    assert cipa.token
    assert cipa.stamped_at == AN
    # Damga gerçekten **bu** özeti taşıyor.
    assert otorite.covers(cipa.token, bytes.fromhex(bas.hash))


def test_bos_gunluk_cipalanmiyor() -> None:
    _, cipalar, servis = _dunya(otorite=SahteOtorite())

    assert servis.anchor_now() is None
    assert cipalar.anchors() == []


def test_damga_alinamazsa_kayit_yine_yaziliyor() -> None:
    """Çıpasız bir gün, çıpalı sanılmasın."""
    gunluk, cipalar, servis = _dunya(otorite=SahteOtorite(patlat=True))
    _olay(gunluk, 1)

    cipa = servis.anchor_now()

    assert cipa is not None
    assert cipa.state == "failed"
    assert cipa.token is None
    assert "Sunucuya ulaşılamadı" in (cipa.error or "")
    assert len(cipalar.anchors()) == 1


def test_cipalama_kapaliyken_sessizce_gecmiyor() -> None:
    """Kapalıyken "güvenli" demiyoruz; komut ve /health durumu söylüyor."""
    gunluk, cipalar, servis = _dunya(otorite=None)
    _olay(gunluk, 1)

    assert not servis.enabled
    assert servis.anchor_now() is None
    assert servis.anchor_due() is None
    assert cipalar.anchors() == []


def test_gunun_ikinci_turunda_tekrar_cipalanmiyor() -> None:
    otorite = SahteOtorite()
    gunluk, cipalar, servis = _dunya(otorite=otorite)
    _olay(gunluk, 1)

    assert servis.anchor_due() is not None
    assert servis.anchor_due() is None
    assert otorite.sayac == 1
    assert len(cipalar.anchors()) == 1


def test_ucuncu_denemeden_sonra_gun_bekleniyor() -> None:
    otorite = SahteOtorite(patlat=True)
    gunluk, cipalar, servis = _dunya(otorite=otorite)
    _olay(gunluk, 1)

    for _ in range(5):
        servis.anchor_due()

    assert otorite.sayac == 3
    assert len(cipalar.anchors()) == 3


# --- doğrulama ----------------------------------------------------------


def test_dogrulama_saglam_zincirde_temiz() -> None:
    gunluk, _, servis = _dunya(otorite=SahteOtorite())
    _olay(gunluk, 1)
    servis.anchor_now()

    rapor = servis.verify()

    assert (rapor.checked, rapor.intact) == (1, True)
    assert rapor.last_at == AN


def test_gecmis_bastan_yazilirsa_cipa_tutmuyor() -> None:
    """Çıpanın tek varlık sebebi: zincirin yeniden hesaplanmasını yakalamak.

    Kaydı değiştirip zinciri baştan **geçerli** biçimde kuran biri
    `verify()` zincir doğrulamasını geçer; çıpa geçemez.
    """
    gunluk, _, servis = _dunya(otorite=SahteOtorite())
    olay = _olay(gunluk, 1)
    servis.anchor_now()

    # Kaydı değiştirip özetini **yeniden hesaplıyoruz**: zincir kendi
    # içinde tutarlı kalıyor, çıpadaki eski kök ise tutmuyor.
    gunluk._events[0] = sealed(tampered(olay, ip="203.0.113.1"))
    rapor = servis.verify()

    assert not rapor.intact
    assert "o tarihten sonra değişmiş" in rapor.problems[0].reason


def test_cipalanan_kayit_silinirse_gorunuyor() -> None:
    gunluk, _, servis = _dunya(otorite=SahteOtorite())
    _olay(gunluk, 1)
    servis.anchor_now()

    gunluk._events.clear()
    rapor = servis.verify()

    assert not rapor.intact
    assert "günlükte yok" in rapor.problems[0].reason


def test_damga_baska_ozete_aitse_yakalaniyor() -> None:
    """Geçerli ama **başka bir veriye** ait bir damga kabul edilmemeli."""
    otorite = SahteOtorite()
    gunluk, cipalar, servis = _dunya(otorite=otorite)
    olay = _olay(gunluk, 1)
    baska = otorite._tsa.damga(hashlib.sha256(b"baska veri").digest(), nonce=1, gen_time=AN)
    cipalar.save_anchor(
        ChainAnchor(
            id=uuid4(),
            created_at=AN,
            sequence=1,
            chain_hash=olay.hash,
            state="ok",
            token=baska,
            stamped_at=AN,
        )
    )

    rapor = servis.verify()

    assert not rapor.intact
    assert "Damga bu özeti taşımıyor" in rapor.problems[0].reason


# --- RFC 3161 istemcisi -------------------------------------------------


def _istemci_ve_tsa(
    monkeypatch: pytest.MonkeyPatch, *, durum: str = "granted", nonce_degistir: bool = False
) -> tuple[Rfc3161Authority, SahteTsa]:
    tsa = SahteTsa()

    class Yanit:
        def __init__(self, govde: bytes) -> None:
            self._govde = govde

        def read(self) -> bytes:
            return self._govde

        def __enter__(self) -> Yanit:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    def sahte_urlopen(istek: object, timeout: int = 0) -> Yanit:
        govde = bytes(istek.data)  # type: ignore[attr-defined]
        if nonce_degistir:
            from asn1crypto import tsp

            ozet = bytes(tsp.TimeStampReq.load(govde)["message_imprint"]["hashed_message"].native)
            return Yanit(tsa.yanit(ozet, nonce=999999))
        return Yanit(tsa.yanitla(govde, durum=durum))

    monkeypatch.setattr("urllib.request.urlopen", sahte_urlopen)
    return Rfc3161Authority("http://tsa.deneme/damga", timeout_seconds=1), tsa


def test_istemci_damgayi_alip_cozuyor(monkeypatch: pytest.MonkeyPatch) -> None:
    istemci, _ = _istemci_ve_tsa(monkeypatch)
    ozet = hashlib.sha256(b"zincir kokudur").digest()

    damga = istemci.stamp(ozet)

    assert istemci.covers(damga.token, ozet)
    assert istemci.signature_ok(damga.token)
    assert damga.stamped_at.tzinfo is not None
    assert damga.serial == "1"


def test_sunucu_reddederse_damga_yok(monkeypatch: pytest.MonkeyPatch) -> None:
    istemci, _ = _istemci_ve_tsa(monkeypatch, durum="rejection")

    with pytest.raises(TimestampError, match="reddetti"):
        istemci.stamp(hashlib.sha256(b"x").digest())


def test_nonce_tutmayan_yanit_reddediliyor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sunucunun hazır bir yanıtı iade etmesi (tekrar oynatma)."""
    istemci, _ = _istemci_ve_tsa(monkeypatch, nonce_degistir=True)

    with pytest.raises(TimestampError, match="Nonce"):
        istemci.stamp(hashlib.sha256(b"x").digest())


def test_kisa_ozet_gonderilmiyor() -> None:
    istemci = Rfc3161Authority("http://tsa.deneme")

    with pytest.raises(TimestampError, match="32 bayt"):
        istemci.stamp(b"kisa")


def test_bozuk_imza_ve_degistirilmis_govde_reddediliyor() -> None:
    """İmza tutsa bile gövde değiştiyse damga geçersiz (RFC 5652 5.4)."""
    tsa = SahteTsa()
    istemci = Rfc3161Authority("http://tsa.deneme")
    ozet = hashlib.sha256(b"x").digest()

    assert istemci.signature_ok(tsa.damga(ozet, nonce=1))
    assert not istemci.signature_ok(tsa.damga(ozet, nonce=1, imzayi_boz=True))
    assert not istemci.signature_ok(tsa.damga(ozet, nonce=1, ozeti_boz=True))
    assert not istemci.signature_ok(b"bu bir damga degil")


def test_damga_baska_sertifikayi_gosteriyorsa_reddediliyor() -> None:
    """RFC 3161 2.4.1: damga imzalayan sertifikayı adıyla da taşır.

    Bu alanı atlayan bir kontrol, imzası geçerli ama **başka bir
    sertifika için** üretilmiş bir damgayı kabul ederdi. OpenSSL de
    alan eksikken damgayı doğrulamıyor (geliştirme sırasında
    `openssl ts -verify` ile karşılaştırılarak bulundu).
    """
    tsa = SahteTsa()
    istemci = Rfc3161Authority("http://tsa.deneme")
    ozet = hashlib.sha256(b"x").digest()

    assert not istemci.signature_ok(tsa.damga(ozet, nonce=1, ess_boz=True))


def test_cope_damga_covers_false_doner() -> None:
    """Çözülemeyen damga "tutuyor" sayılmamalı."""
    assert not Rfc3161Authority("http://yok").covers(b"\x00\x01", b"a" * 32)


# --- uçtan uca ----------------------------------------------------------


@pytest.fixture
def cipali_istemci(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> TestClient:
    """Çıpalama açık bir uygulama: otorite sahte, gerisi gerçek."""
    uygulama = create_app(Settings(evidence_dir=str(tmp_path), tsa_url="http://tsa.deneme"))
    monkeypatch.setattr(bagimliliklar, "_damga_otoritesi", lambda: SahteOtorite())
    return TestClient(uygulama)


def test_zamanlayici_turu_gunde_bir_cipa_aliyor(
    cipali_istemci: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """İki tur, **tek** çıpa.

    İlk turu kimin attığı önemli değil (geliştirmede ilk istek de bir
    tur atıyor); sınanan şey günde bir kez alınması.

    Saat sabitleniyor: çıpa yerel 04:00'ten önce alınmıyor (FR-1302),
    yani duvardaki saate bırakılırsa bu test gece yarısı ile 04:00
    arasında düşüyordu — tam da kapanış vardiyasının çalıştığı saatler.
    """
    # Saat kapısı kaldırılıyor: çıpa yerel 04:00'ten önce alınmıyor
    # (FR-1302), yani duvardaki saate bırakılırsa bu test gece yarısı
    # ile 04:00 arasında düşüyordu — tam da kapanış vardiyasının
    # çalıştığı saatler. Sınanan şey saat değil, günde bir kez olması.
    monkeypatch.setattr(chain_anchor, "ANCHOR_HOUR", 0)
    istemci = oturum_ac(cipali_istemci)

    istemci.post("/api/v1/scheduler/tick")
    ikinci = istemci.post("/api/v1/scheduler/tick").json()

    assert ikinci["anchored"] == 0
    servis = bagimliliklar.cipa_servisi()
    assert len(servis.recent()) == 1
    assert servis.recent()[0].state == "ok"
    assert servis.verify().intact


def test_health_cipalamanin_acik_olup_olmadigini_soyluyor(cipali_istemci: TestClient) -> None:
    """Kapalıyken sessizce "güvenli" demiyoruz."""
    acik = cipali_istemci.get("/api/v1/health").json()
    kapali = TestClient(create_app(Settings())).get("/api/v1/health").json()

    assert acik["timestamping_configured"] is True
    assert kapali["timestamping_configured"] is False


def test_cipa_gunluk_degisirse_komutla_gorunur(cipali_istemci: TestClient) -> None:
    """`izi_dogrula` zinciri de çıpayı da sınıyor."""
    from talimatname import izi_dogrula

    oturum_ac(cipali_istemci).post("/api/v1/scheduler/tick")

    assert izi_dogrula.kosu([]) == 0

    gunluk = bagimliliklar._izi_deposu()
    olay = gunluk.events(limit=1)[0]  # type: ignore[attr-defined]
    gunluk._events[0] = sealed(tampered(olay, ip="203.0.113.9"))  # type: ignore[attr-defined]

    assert izi_dogrula.kosu([]) == 1


def test_sure_dolmadan_ikinci_tur_damga_sunucusuna_gitmiyor(
    cipali_istemci: TestClient,
) -> None:
    """Zamanlayıcı dakikada bir koşuyor; damga günde bir alınıyor."""
    istemci = oturum_ac(cipali_istemci)
    istemci.post("/api/v1/scheduler/tick")
    otorite = bagimliliklar._damga_otoritesi()
    assert isinstance(otorite, SahteOtorite)
    once = otorite.sayac

    istemci.post("/api/v1/scheduler/tick")

    assert otorite.sayac == once


def test_cipalama_kapaliyken_tur_calisiyor(tmp_path: object) -> None:
    """TSA yoksa tur yine koşuyor: çıpa ürünün kendisi değil."""
    istemci = oturum_ac(TestClient(create_app(Settings(evidence_dir=str(tmp_path)))))

    tur = istemci.post("/api/v1/scheduler/tick")

    assert tur.status_code == 200
    assert tur.json()["anchored"] == 0
