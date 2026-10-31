"""Bekleyen kanıt süpürücüsü (FR-0614 tekillik kilidi).

İddia: **yarıda kalan bir yükleme, aynı fotoğrafı sonsuza dek
yasaklamamalı.**

`start()` kaydı yüklemeden önce açıyor ve özet tekilliğini o anda
kilitliyor. İstemci baytları hiç göndermezse kayıt `pending` kalıyor
ve kilidi tutuyor: kullanıcı aynı kareyi bir daha yüklemek istediğinde
"bu dosya daha önce yüklendi" diyen, ama ortada dosya olmayan bir
duvara çarpıyor.

İkinci iddia: **depoda duran bayt kanıttır, silinmez.** İstemci
yüklemeyi bitirip `complete` demeden düşmüş olabilir; süpürücü önce
depoya bakar ve özet tutuyorsa kaydı tamamlar.
"""

from __future__ import annotations

import hashlib
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from PIL import Image

from talimatname.infra.memory import (
    MemoryEvidenceRepository,
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemoryTemplateRepository,
    MemoryUserRepository,
    sabit_id,
)
from talimatname.services.evidence import DuplicateEvidence, EvidenceService
from talimatname.services.plans import PlanService
from talimatname.services.storage import LocalObjectStore
from talimatname.settings import Settings

KADIKOY = sabit_id("sube:KDK")
MADDE = sabit_id("madde:1")


def _resim(renk: tuple[int, int, int] = (40, 90, 140)) -> tuple[bytes, str]:
    tampon = io.BytesIO()
    Image.new("RGB", (120, 80), renk).save(tampon, format="JPEG")
    baytlar = tampon.getvalue()
    return baytlar, hashlib.sha256(baytlar).hexdigest()


class Dunya:
    """Zamanı elde tutuyoruz: süpürücü eşiği gün ölçeğinde.

    Başlangıç **geçmişte**: yükleme belirteci o anın saatiyle
    imzalanıyor ve gelecek tarihli belirteç geçersiz sayılır.
    """

    def __init__(self, tmp: Path) -> None:
        self.an = datetime.now(UTC) - timedelta(days=30)
        self.planlar = MemoryPlanRepository()
        self.org = MemoryOrganizationRepository()
        self.kanitlar = MemoryEvidenceRepository()
        PlanService(
            self.planlar, self.org, MemoryTemplateRepository(), now=lambda: self.an
        ).generate_all()
        self.depo = LocalObjectStore(tmp)
        self.servis = EvidenceService(
            self.kanitlar,
            self.planlar,
            self.org,
            self.depo,
            MemoryUserRepository(),
            settings=Settings(environment="dev"),
            now=lambda: self.an,
        )
        self.run_id = next(r for r in self.planlar.runs() if r.branch_id == KADIKOY).id

    def ilerle(self, gun: int) -> None:
        self.an += timedelta(days=gun)

    def baslat(self, baytlar: bytes, ozet: str) -> tuple[UUID, str]:
        """Yalnızca `start`: bayt gönderilmiyor — yarıda kalmış yükleme."""
        kanit, belirtec = self.servis.start(
            run_id=self.run_id,
            answer_id=uuid4(),
            item_id=MADDE,
            sha256=ozet,
            content_type="image/jpeg",
            size_bytes=len(baytlar),
        )
        return kanit.id, belirtec


@pytest.fixture
def dunya(tmp_path: Path) -> Dunya:
    return Dunya(tmp_path)


def test_bayti_gelmeyen_kayit_supurulur(dunya: Dunya) -> None:
    baytlar, ozet = _resim()
    dunya.baslat(baytlar, ozet)

    dunya.ilerle(8)
    sayac = dunya.servis.sweep_pending()

    assert sayac == {"incelenen": 1, "kurtarilan": 0, "silinen": 1}
    assert dunya.kanitlar.evidences() == []


def test_supurulunce_ayni_fotograf_yeniden_yuklenebilir(dunya: Dunya) -> None:
    """Asıl mesele bu: kilit kalkmazsa kullanıcı çakılı kalırdı."""
    baytlar, ozet = _resim()
    dunya.baslat(baytlar, ozet)

    with pytest.raises(DuplicateEvidence):
        dunya.baslat(baytlar, ozet)

    dunya.ilerle(8)
    dunya.servis.sweep_pending()

    kanit_id, _ = dunya.baslat(baytlar, ozet)  # artık serbest
    assert kanit_id


def test_taze_bekleyen_kayda_dokunulmaz(dunya: Dunya) -> None:
    """Yükleme yoldaysa süpürmek, kanıtı yolda öldürmek olurdu."""
    baytlar, ozet = _resim()
    dunya.baslat(baytlar, ozet)

    dunya.ilerle(2)
    sayac = dunya.servis.sweep_pending()

    assert sayac["silinen"] == 0
    assert len(dunya.kanitlar.evidences()) == 1


def test_depodaki_bayt_silinmez_tamamlanir(dunya: Dunya) -> None:
    """İstemci `complete` demeden düşmüş: bayt gerçek kanıt, atılmaz."""
    baytlar, ozet = _resim()
    kanit_id, _ = dunya.baslat(baytlar, ozet)
    # Bayt kovaya yazılmış ama `complete` hiç çağrılmamış: istemci
    # yüklemeden sonra, doğrulamadan önce düşmüş.
    dunya.depo.put(dunya.servis.get(kanit_id).storage_key, baytlar)

    dunya.ilerle(8)
    sayac = dunya.servis.sweep_pending()

    assert sayac == {"incelenen": 1, "kurtarilan": 1, "silinen": 0}
    (kanit,) = dunya.kanitlar.evidences()
    assert kanit.status == "stored"
    assert dunya.depo.get(kanit.storage_key) == baytlar


def test_yarim_bayt_kayitla_birlikte_gider(dunya: Dunya) -> None:
    """Özet tutmuyorsa o bayt kanıt değil: kopyası da kaydı da silinir."""
    baytlar, ozet = _resim()
    kanit_id, _ = dunya.baslat(baytlar, ozet)
    anahtar = dunya.servis.get(kanit_id).storage_key
    dunya.depo.put(anahtar, b"yarim")

    dunya.ilerle(8)
    sayac = dunya.servis.sweep_pending()

    assert sayac["silinen"] == 1
    assert dunya.kanitlar.evidences() == []
    assert not dunya.depo.exists(anahtar)


def test_tur_sinirli_kalir(dunya: Dunya) -> None:
    """Tur uzun sürerse zamanlayıcının öbür işleri gecikir."""
    for sira in range(5):
        baytlar, ozet = _resim(renk=(sira * 20, 60, 90))
        dunya.baslat(baytlar, ozet)

    dunya.ilerle(8)
    sayac = dunya.servis.sweep_pending(limit=2)

    assert sayac["incelenen"] == 2
    assert len(dunya.kanitlar.evidences()) == 3


def test_esik_disaridan_verilebilir(dunya: Dunya) -> None:
    baytlar, ozet = _resim()
    dunya.baslat(baytlar, ozet)

    dunya.ilerle(2)
    sayac = dunya.servis.sweep_pending(older_than=timedelta(days=1))

    assert sayac["silinen"] == 1
