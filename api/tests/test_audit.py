"""Olay günlüğü ve hash zinciri (ST-099, ST-100; FR-1301, FR-1304; TC-100, TC-101).

İddia: **kayıt sonradan değiştirilmemiştir — değiştirilmişse görünür.**

Bir denetim izinin tek değeri bu cümleyi söyleyebilmek. Testler de o
cümleyi sınıyor: zinciri kurup bir kaydı elle bozuyor ve kırılmanın
hangi kayıtta olduğunun raporlandığını kontrol ediyor.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from talimatname.domain.audit import (
    GENESIS,
    AuditEvent,
    SequenceTaken,
    chain_hash,
    sealed,
    summary_of,
)
from talimatname.domain.validation import ValidationError
from talimatname.infra.memory import MemoryAuditRepository
from talimatname.services.audit import AuditService, RequestContext, tampered

AN = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)
CALISTIRMA = UUID("11111111-1111-5111-8111-111111111111")
KISI = UUID("22222222-2222-5222-8222-222222222222")


def _servis(an: datetime = AN) -> tuple[AuditService, MemoryAuditRepository]:
    depo = MemoryAuditRepository()
    saat = [an]
    servis = AuditService(depo, now=lambda: saat[0])
    return servis, depo


# --- zincir (FR-1301) --------------------------------------------------


def test_ilk_olay_genesisten_baslar() -> None:
    servis, _ = _servis()

    olay = servis.record("oturum.acildi", object_type="kullanici", object_id=KISI)

    assert olay is not None
    assert olay.sequence == 1
    assert olay.prev_hash == GENESIS
    assert olay.hash == chain_hash(olay)


def test_her_olay_oncekinin_ozetini_tasir() -> None:
    servis, _ = _servis()

    bir = servis.record("oturum.acildi", object_type="kullanici", object_id=KISI)
    iki = servis.record("calistirma.gonderildi", object_type="calistirma", object_id=CALISTIRMA)

    assert bir is not None
    assert iki is not None
    assert iki.prev_hash == bir.hash
    assert iki.sequence == 2


def test_ayni_icerik_ayni_ozeti_verir() -> None:
    """Özet içerikten türüyor: aynı kayıt iki makinede aynı özeti verir."""
    olay = AuditEvent(
        id=CALISTIRMA,
        sequence=1,
        event_type="oturum.acildi",
        at=AN,
        object_type="kullanici",
        object_id=KISI,
    )

    assert chain_hash(olay) == chain_hash(olay)
    assert chain_hash(olay) != chain_hash(tampered(olay, sequence=2))


def test_turkce_ozet_ozeti_degistirir() -> None:
    """Kanonik gösterim JSON: içinde ayırıcı geçen metin zinciri bozmaz."""
    temel = sealed(
        AuditEvent(
            id=CALISTIRMA,
            sequence=1,
            event_type="personel.guncellendi",
            at=AN,
            object_type="kullanici",
            after={"not": "Şube|müdürü"},
        )
    )
    benzer = sealed(tampered(temel, after={"not": "Şube", "ek": "müdürü"}, hash=""))

    assert temel.hash != benzer.hash


# --- doğrulama (FR-1304, TC-101) ---------------------------------------


def test_bozulmamis_zincir_dogrulanir() -> None:
    servis, _ = _servis()
    for _ in range(50):
        servis.record("kanit.alindi", object_type="kanit", object_id=uuid4())

    rapor = servis.verify()

    assert rapor.checked == 50
    assert rapor.intact is True
    assert (rapor.first_sequence, rapor.last_sequence) == (1, 50)


def test_degistirilmis_kayit_kirilma_olarak_raporlanir() -> None:
    """TC-101: bir kaydı elle değiştir → kırılma noktası raporlanır."""
    servis, depo = _servis()
    for _ in range(5):
        servis.record("kanit.alindi", object_type="kanit", object_id=uuid4())

    # Üçüncü kaydın içeriği değişiyor, özeti olduğu gibi bırakılıyor:
    # günlüğü "düzeltmeye" çalışan birinin yapacağı şey.
    depo._events[2] = tampered(depo._events[2], after={"deger": "sonradan yazıldı"})

    rapor = servis.verify()

    # Kırılma **tam** o kayıtta: sonrakiler gürültü yapmıyor, çünkü
    # zincir saklanan özetten ilerliyor. Denetim konuşmasında
    # "üçüncü kayıt değişmiş" demek, "zincir bozuk" demekten yararlı.
    assert rapor.intact is False
    assert [k.sequence for k in rapor.breaks] == [3]
    assert "içerik değişmiş" in rapor.breaks[0].reason


def test_silinen_kayit_sira_atlamasiyla_gorunur() -> None:
    """Satır silmek de görünür: sıra boşluğu zincirin kendisi kadar delil."""
    servis, depo = _servis()
    for _ in range(4):
        servis.record("kanit.alindi", object_type="kanit", object_id=uuid4())
    del depo._events[1]

    rapor = servis.verify()

    assert rapor.intact is False
    assert rapor.breaks[0].sequence == 3
    assert "atlamış" in rapor.breaks[0].reason


def test_buyuk_gunlukte_dogrulama_tutarli() -> None:
    """TC-101 ölçeği: zincir uzadıkça doğrulama bozulmamalı."""
    servis, _ = _servis()
    for _ in range(2_000):
        servis.record("kanit.alindi", object_type="kanit", object_id=CALISTIRMA)

    rapor = servis.verify(limit=5_000)

    assert (rapor.checked, rapor.intact) == (2_000, True)


# --- ekle-yalnızlık (TC-100) -------------------------------------------


def test_depo_portunda_guncelleme_ve_silme_yok() -> None:
    """Ekle-yalnızlık kodun şeklinde de duruyor, yalnızca yetkide değil."""
    from talimatname.services.audit import AuditRepository

    yuzey = {ad for ad in vars(AuditRepository) if not ad.startswith("_")}

    assert yuzey == {"append", "head", "events"}


def test_ayni_sira_ikinci_kez_yazilamaz() -> None:
    depo = MemoryAuditRepository()
    olay = sealed(
        AuditEvent(id=uuid4(), sequence=1, event_type="oturum.acildi", at=AN, object_type="x")
    )
    depo.append(olay)

    with pytest.raises(SequenceTaken):
        depo.append(sealed(tampered(olay, id=uuid4(), hash="")))


def test_sira_cakismasinda_yeniden_denenir() -> None:
    """İki istek aynı anda yazarsa zincir çatallanmamalı.

    Depo ilk denemede "sıra alınmış" diyor; servis başı yeniden okuyup
    bir sonraki halkaya yazmalı.
    """
    depo = MemoryAuditRepository()
    servis = AuditService(depo, now=lambda: AN)
    servis.record("oturum.acildi", object_type="kullanici")

    cakisma = {"kalan": 1}
    gercek_append = depo.append

    def bir_kez_cakis(event: AuditEvent) -> None:
        if cakisma["kalan"]:
            cakisma["kalan"] = 0
            raise SequenceTaken("deneme")
        gercek_append(event)

    depo.append = bir_kez_cakis  # type: ignore[method-assign]
    olay = servis.record("kanit.alindi", object_type="kanit")

    assert olay is not None
    assert olay.sequence == 2
    assert servis.verify().intact is True


# --- içerik (FR-1301) ---------------------------------------------------


def test_istek_baglami_kaydediliyor() -> None:
    """ "Nereden" sorusu denetim izinin yarısı: IP ve cihaz."""
    servis, _ = _servis()

    olay = servis.record(
        "oturum.acildi",
        object_type="kullanici",
        object_id=KISI,
        context=RequestContext(actor_id=KISI, ip="198.51.100.7", device="iPhone"),
    )

    assert olay is not None
    assert (olay.actor_id, olay.ip, olay.device) == (KISI, "198.51.100.7", "iPhone")


def test_zamanlayici_olayinda_ip_uydurulmaz() -> None:
    """Tur işinde IP yok; boş bırakmak, var gibi yazmaktan dürüst."""
    servis, _ = _servis()

    olay = servis.record("kanit.supuruldu", object_type="kanit", object_id=uuid4())

    assert olay is not None
    assert (olay.ip, olay.device, olay.actor_id) == (None, None, None)


def test_ozet_yalnizca_degiseni_tutar() -> None:
    once, sonra = summary_of(
        {"rol": "staff", "sube": "KDK"},
        {"rol": "branch_manager", "sube": "KDK"},
    )

    assert once == {"rol": "staff"}
    assert sonra == {"rol": "branch_manager"}


def test_bilinmeyen_olay_turu_reddedilir() -> None:
    """Tür adı sözleşme: doğrulama sayfası ve ekran ona göre yazılıyor."""
    with pytest.raises(ValidationError):
        sealed(
            AuditEvent(id=uuid4(), sequence=1, event_type="uydurma.olay", at=AN, object_type="x")
        )


def test_nesnenin_izi_okunabiliyor() -> None:
    servis, _ = _servis()
    servis.record("calistirma.gonderildi", object_type="calistirma", object_id=CALISTIRMA)
    servis.record("kanit.alindi", object_type="kanit", object_id=uuid4())
    servis.record("calistirma.kacirildi", object_type="calistirma", object_id=CALISTIRMA)

    iz = servis.for_object(CALISTIRMA)

    assert [o.event_type for o in iz] == ["calistirma.gonderildi", "calistirma.kacirildi"]


def test_aralikla_dogrulama_oncekinin_ozetini_bekler() -> None:
    """Son ayı doğrulamak için bütün günlüğü okumak gerekmesin."""
    depo = MemoryAuditRepository()
    saat = [AN]
    servis = AuditService(depo, now=lambda: saat[0])
    for gun in range(6):
        saat[0] = AN + timedelta(days=gun)
        servis.record("kanit.alindi", object_type="kanit", object_id=uuid4())

    rapor = servis.verify(since=AN + timedelta(days=3))

    assert rapor.checked == 3
    assert rapor.intact is True


def test_gunluk_yazilamazsa_is_durmaz() -> None:
    """Denetim izi değerli ama ürünün kendisi değil.

    Günlük tablosundaki bir aksaklık, kanıt yüklemeyi ya da oturum
    açmayı düşürmemeli; olay kaybolur, `verify` bunu zaten gösterir.
    """

    class BozukDepo(MemoryAuditRepository):
        def append(self, event: AuditEvent) -> None:
            raise RuntimeError("veritabanı yok")

    servis = AuditService(BozukDepo(), now=lambda: AN)

    assert servis.record("oturum.acildi", object_type="kullanici") is None


# --- doğrulama komutu (ST-100, FR-1304) --------------------------------


def test_komut_butun_zincirde_sifir_doner(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from talimatname import izi_dogrula

    servis, _ = _servis()
    for _ in range(3):
        servis.record("kanit.alindi", object_type="kanit", object_id=uuid4())
    monkeypatch.setattr(izi_dogrula, "izi_servisi", lambda: servis)

    cikis = izi_dogrula.kosu([])

    assert cikis == 0
    assert "Zincir bütün" in capsys.readouterr().out


def test_komut_kirilmada_bir_doner(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Çıkış kodu konuşuyor: izleme ve CI metin ayrıştırmasın."""
    from talimatname import izi_dogrula

    servis, depo = _servis()
    for _ in range(3):
        servis.record("kanit.alindi", object_type="kanit", object_id=uuid4())
    depo._events[1] = tampered(depo._events[1], after={"deger": "sonradan"})
    monkeypatch.setattr(izi_dogrula, "izi_servisi", lambda: servis)

    cikis = izi_dogrula.kosu([])

    assert cikis == 1
    yazi = capsys.readouterr().out
    assert "ZİNCİR KIRIK" in yazi
    assert "sıra 2" in yazi


def test_komut_bos_gunlukte_de_calisir(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from talimatname import izi_dogrula

    servis, _ = _servis()
    monkeypatch.setattr(izi_dogrula, "izi_servisi", lambda: servis)

    assert izi_dogrula.kosu([]) == 0
    assert "Günlük boş" in capsys.readouterr().out
