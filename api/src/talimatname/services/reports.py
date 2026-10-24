"""Rapor servisi (ST-088, ST-145; FR-1207, FR-1220, FR-1208).

Üç soruyu cevaplıyor ve üçü de denetim konuşmasının parçası:

* **Bu ay nasıl geçti?** Zamanında / geç / kaçırıldı dağılımı, şube
  kırılımı (FR-1220).
* **Sıcaklıklar ne durumda?** Ölçüm zaman serisi, aralık dışı işaretli
  (FR-1207). Gıda güvenliği denetiminde istenen tam olarak bu.
* **Kanıtı göster.** Şube ve tarih süzgeciyle kanıt ızgarası (FR-1208).

Sayma işi alanda (`domain/reports`), burada yalnızca **okuma ve
birleştirme** var. Rapor kendi "geç" tanımını yazmıyor: panonun
kullandığı `Run.state_at` türetmesini kullanıyor, yoksa iki ekran aynı
güne iki farklı cevap verirdi.

Okumalar **aralıkla** yapılıyor (`runs_between`, `answers_for_runs`):
çalıştırma başına ayrı sorgu, 200 çalıştırmalık bir ayda 200
gidiş-dönüş demekti.
"""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from talimatname.domain.evidence import Evidence
from talimatname.domain.reports import (
    BranchSummary,
    Counters,
    Measurement,
    MonthlySummary,
    measurement,
    outcome,
)
from talimatname.domain.templates import Item
from talimatname.services.evidence import EvidenceRepository
from talimatname.services.execution import AnswerRepository
from talimatname.services.organization import OrganizationRepository
from talimatname.services.plans import PlanRepository
from talimatname.services.templates import TemplateRepository

#: Ölçüm günlüğünde en çok kaç nokta döner. Denetim dönemi uzun
#: olabiliyor; ekranı ve yanıtı sınırsız bırakmıyoruz.
MAX_MEASUREMENTS = 2_000


@dataclass(frozen=True, slots=True)
class MeasurementSeries:
    """Bir maddenin zaman serisi: aynı ekipmanın aynı ölçümü."""

    item_id: UUID
    item_title: str
    unit: str | None
    min_value: float | None
    max_value: float | None
    points: tuple[Measurement, ...]

    @property
    def out_of_range_count(self) -> int:
        return sum(1 for nokta in self.points if nokta.out_of_range)


class ReportService:
    def __init__(
        self,
        plans: PlanRepository,
        answers: AnswerRepository,
        templates: TemplateRepository,
        org: OrganizationRepository,
        evidence: EvidenceRepository | None = None,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._plans = plans
        self._answers = answers
        self._templates = templates
        self._org = org
        self._evidence = evidence
        self._now = now

    # --- aylık özet (FR-1220) ----------------------------------------

    def monthly(
        self, year: int, month: int, *, branch_ids: set[UUID] | None = None
    ) -> MonthlySummary:
        """Bir ayın tek sayfalık özeti.

        Açık pencereler yüzdeye **girmiyor**: ayın ortasındayken
        "yüzde 50 zamanında" demek, henüz olmamış işi kayıp saymaktır.
        """
        ilk = date(year, month, 1)
        son = date(year, month, monthrange(year, month)[1])
        an = self._now()

        kosular = [
            r
            for r in self._plans.runs_between(ilk, son)
            if branch_ids is None or r.branch_id in branch_ids
        ]
        cevaplar = self._answers.answers_for_runs([r.id for r in kosular])

        toplam = Counters()
        sube_sayaclari: dict[UUID, Counters] = {}
        for run in kosular:
            sonuc = outcome(run, an)
            run_cevaplari = cevaplar.get(run.id, [])
            yapilamadi = sum(1 for c in run_cevaplari if c.state == "not_done")
            basarisiz = run.result == "failed"
            toplam = toplam.plus(sonuc, failed=basarisiz, not_done=yapilamadi)
            sube_sayaclari[run.branch_id] = sube_sayaclari.get(run.branch_id, Counters()).plus(
                sonuc, failed=basarisiz, not_done=yapilamadi
            )

        subeler = {s.id: s for s in self._org.branches()}
        kirilim = tuple(
            BranchSummary(
                branch_id=sube_id,
                branch_code=subeler[sube_id].code if sube_id in subeler else "—",
                branch_name=subeler[sube_id].name if sube_id in subeler else "Bilinmeyen şube",
                counters=sayac,
            )
            for sube_id, sayac in sube_sayaclari.items()
        )
        return MonthlySummary(
            year=year,
            month=month,
            first_day=ilk,
            last_day=son,
            counters=toplam,
            branches=kirilim,
        )

    # --- ölçüm günlüğü (FR-1207) -------------------------------------

    def measurements(
        self,
        *,
        first_day: date,
        last_day: date,
        branch_ids: set[UUID] | None = None,
        only_out_of_range: bool = False,
    ) -> tuple[MeasurementSeries, ...]:
        """Sıcaklık ve sayı maddelerinin zaman serisi (denetim çıktısı).

        Madde **kimliğine** göre gruplanıyor: aynı şablon sürümündeki
        "Süt dolabı sıcaklığı" tek seri olur, şube şube dağılmaz.
        """
        kosular = [
            r
            for r in self._plans.runs_between(first_day, last_day)
            if branch_ids is None or r.branch_id in branch_ids
        ]
        if not kosular:
            return ()

        cevaplar = self._answers.answers_for_runs([r.id for r in kosular])
        maddeler = self._maddeler({r.template_version_id for r in kosular})

        seriler: dict[UUID, list[Measurement]] = {}
        for run in kosular:
            for cevap in cevaplar.get(run.id, []):
                madde = maddeler.get(cevap.item_id)
                if madde is None:
                    continue
                nokta = measurement(cevap, madde, run)
                if nokta is None:
                    continue
                if only_out_of_range and not nokta.out_of_range:
                    continue
                seriler.setdefault(madde.id, []).append(nokta)

        sonuc: list[MeasurementSeries] = []
        for madde_id, noktalar in seriler.items():
            madde = maddeler[madde_id]
            sirali = sorted(
                noktalar, key=lambda n: n.measured_at or datetime.min.replace(tzinfo=UTC)
            )
            sonuc.append(
                MeasurementSeries(
                    item_id=madde.id,
                    item_title=madde.title,
                    unit=madde.unit,
                    min_value=madde.min_value,
                    max_value=madde.max_value,
                    points=tuple(sirali[:MAX_MEASUREMENTS]),
                )
            )
        # Aralık dışı olanı olan seriler önce: denetim oradan başlıyor.
        sonuc.sort(key=lambda s: (-s.out_of_range_count, s.item_title))
        return tuple(sonuc)

    # --- kanıt galerisi (FR-1208) ------------------------------------

    def gallery(
        self,
        *,
        first_day: date,
        last_day: date,
        branch_ids: set[UUID] | None = None,
        only_flagged: bool = False,
    ) -> tuple[Evidence, ...]:
        """Şube ve tarih süzgeciyle kanıtlar; yenisi önce.

        Yalnızca **doğrulanmış** kanıt: `pending` bir niyet beyanıdır,
        baytları depoda değildir (ST-054).
        """
        if self._evidence is None:
            return ()
        kosular = {
            r.id
            for r in self._plans.runs_between(first_day, last_day)
            if branch_ids is None or r.branch_id in branch_ids
        }
        kanitlar = [
            k
            for k in self._evidence.evidences()
            if k.run_id in kosular and k.status in ("stored", "stamped")
        ]
        if only_flagged:
            kanitlar = [k for k in kanitlar if k.flags]
        kanitlar.sort(key=lambda k: k.created_at, reverse=True)
        return tuple(kanitlar)

    # --- yardımcılar --------------------------------------------------

    def _maddeler(self, version_ids: set[UUID]) -> dict[UUID, Item]:
        maddeler: dict[UUID, Item] = {}
        for surum_id in version_ids:
            surum = self._templates.version(surum_id)
            if surum is None:
                continue
            for madde in surum.items:
                maddeler[madde.id] = madde
        return maddeler
