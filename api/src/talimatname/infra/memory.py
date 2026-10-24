"""Bellek içi kalıcılık adaptörü — **yalnızca geliştirme ve test**.

Veritabanı ücretsiz bulut PostgreSQL'e taşınana kadar (ADR-0012 md.2)
panel bu adaptörle geliştirilir. Taşındığında yalnızca bu dosyanın
PostgreSQL karşılığı yazılır: servis katmanı ve testler değişmez
(`OrganizationRepository` portu).

Tohum veri, test verisi belgesindeki (06-test/03) **Kahve Durağı** örnek
zinciridir. Gerçek kişi ve müşteri verisi yoktur: adlar uydurmadır ve
şube adları semttir (ADR-0003).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid5

from talimatname.domain.actions import Action
from talimatname.domain.answers import Answer, RunLock
from talimatname.domain.evidence import Evidence
from talimatname.domain.notifications import Notification
from talimatname.domain.organization import Branch, Region, Station, uniform_hours
from talimatname.domain.plans import Assignment, Plan, Run
from talimatname.domain.templates import (
    ChoiceOption,
    Item,
    Section,
    Template,
    TemplateVersion,
)
from talimatname.domain.users import RoleAssignment, User
from talimatname.domain.window import Anchor, BusinessHours, WindowRule

# Tohum kimlikleri sabit: her açılışta aynı id'ler gelsin ki panel
# yenilenince bağlantılar kırılmasın (uuid5, sabit ad alanı).
AD_ALANI = UUID("6f1f6e6a-0a3a-4b1f-9a7d-5f4a2c3d1e00")


def sabit_id(ad: str) -> UUID:
    return uuid5(AD_ALANI, ad)


def _tohum_bolgeler() -> list[Region]:
    return [
        Region(id=sabit_id("bolge:avrupa"), name="Avrupa", code="AVR"),
        Region(id=sabit_id("bolge:anadolu"), name="Anadolu", code="ANA"),
        Region(id=sabit_id("bolge:ege"), name="Ege", code="EGE"),
    ]


def _tohum_subeler() -> list[Branch]:
    standart = uniform_hours(time(8, 0), time(23, 0))
    gec_kapanan = uniform_hours(time(8, 0), time(1, 0))
    pazar_kapali = uniform_hours(time(9, 0), time(21, 0), closed=(6,))

    #: Koordinatlar semt merkezlerine yakın **yaklaşık** değerler: kanıtın
    #: "konum şube dışında" bayrağı (FR-0615) ölçüye dayansın diye var.
    #: Şubeler uydurma (ADR-0003); bu noktalar gerçek bir adres değildir.
    tanim: list[tuple[str, str, str, dict[int, BusinessHours | None], float, float]] = [
        ("KDK", "Kadıköy", "anadolu", standart, 40.9903, 29.0275),
        ("USK", "Üsküdar", "anadolu", standart, 41.0254, 29.0152),
        ("ATS", "Ataşehir", "anadolu", pazar_kapali, 40.9923, 29.1270),
        ("BSK", "Beşiktaş", "avrupa", gec_kapanan, 41.0430, 29.0094),
        ("BKR", "Bakırköy", "avrupa", standart, 40.9819, 28.8772),
        ("SSL", "Şişli", "avrupa", gec_kapanan, 41.0602, 28.9877),
        ("ALS", "Alsancak", "ege", standart, 38.4379, 27.1430),
        ("BRN", "Bornova", "ege", pazar_kapali, 38.4700, 27.2200),
    ]
    return [
        Branch(
            id=sabit_id(f"sube:{kod}"),
            code=kod,
            name=ad,
            timezone="Europe/Istanbul",
            business_hours=saatler,
            region_id=sabit_id(f"bolge:{bolge}"),
            address=f"{ad}, İstanbul" if bolge != "ege" else f"{ad}, İzmir",
            latitude=enlem,
            longitude=boylam,
        ).validated()
        for kod, ad, bolge, saatler, enlem, boylam in tanim
    ]


def _tohum_istasyonlar(subeler: list[Branch]) -> list[Station]:
    sablon: list[tuple[str, str]] = [
        ("Mutfak", "kitchen"),
        ("Bar", "bar"),
        ("Salon", "hall"),
        ("Depo", "storage"),
    ]
    return [
        Station(
            id=sabit_id(f"istasyon:{sube.code}:{ad}"),
            branch_id=sube.id,
            name=ad,
            kind=tur,  # type: ignore[arg-type]
        )
        for sube in subeler
        for ad, tur in sablon
    ]


class MemoryOrganizationRepository:
    """`OrganizationRepository` portunun bellek içi karşılığı."""

    def __init__(self, *, seed: bool = True) -> None:
        self._regions: dict[UUID, Region] = {}
        self._branches: dict[UUID, Branch] = {}
        self._stations: dict[UUID, Station] = {}
        if seed:
            self.load_seed()

    def load_seed(self) -> None:
        for bolge in _tohum_bolgeler():
            self._regions[bolge.id] = bolge
        subeler = _tohum_subeler()
        for sube in subeler:
            self._branches[sube.id] = sube
        for istasyon in _tohum_istasyonlar(subeler):
            self._stations[istasyon.id] = istasyon

    # --- port ---------------------------------------------------------

    def regions(self) -> list[Region]:
        return list(self._regions.values())

    def branches(self) -> list[Branch]:
        return list(self._branches.values())

    def branch(self, branch_id: UUID) -> Branch | None:
        return self._branches.get(branch_id)

    def branch_by_code(self, code: str) -> Branch | None:
        return next((b for b in self._branches.values() if b.code == code), None)

    def save_branch(self, branch: Branch) -> None:
        self._branches[branch.id] = branch

    def stations(self, branch_id: UUID) -> list[Station]:
        return [s for s in self._stations.values() if s.branch_id == branch_id]


def _tohum_kullanicilar() -> list[User]:
    """Örnek personel. Adlar **uydurmadır**; gerçek kişi verisi yoktur (ADR-0003)."""
    tanim: list[tuple[str, str, str | None, list[RoleAssignment]]] = [
        (
            "Cem Yönetici",
            "+905321110001",
            "cem@ornek.test",
            [RoleAssignment("admin")],
        ),
        (
            "Murat Bölge",
            "+905321110002",
            "murat@ornek.test",
            [RoleAssignment("region_manager", sabit_id("bolge:anadolu"))],
        ),
        (
            "Ayşe Şube",
            "+905321110003",
            None,
            [RoleAssignment("branch_manager", sabit_id("sube:KDK"))],
        ),
        (
            "Deniz Şube",
            "+905321110004",
            None,
            [RoleAssignment("branch_manager", sabit_id("sube:BSK"))],
        ),
        (
            "Emre Personel",
            "+905321110005",
            None,
            [RoleAssignment("staff", sabit_id("sube:KDK"))],
        ),
        (
            "Zeynep Personel",
            "+905321110006",
            None,
            [RoleAssignment("staff", sabit_id("sube:KDK"))],
        ),
        (
            "Selin Personel",
            "+905321110007",
            None,
            [RoleAssignment("staff", sabit_id("sube:BSK"))],
        ),
    ]
    return [
        User(
            id=sabit_id(f"kullanici:{telefon}"),
            full_name=ad,
            phone=telefon,
            email=eposta,
            assignments=tuple(atamalar),
        ).validated()
        for ad, telefon, eposta, atamalar in tanim
    ]


class MemoryUserRepository:
    """`UserRepository` portunun bellek içi karşılığı."""

    def __init__(self, *, seed: bool = True) -> None:
        self._users: dict[UUID, User] = {}
        self._mask_counter = 4820  # tohum numarası: maskeleme etiketleri sıradan görünsün
        if seed:
            for kullanici in _tohum_kullanicilar():
                self._users[kullanici.id] = kullanici

    def users(self) -> list[User]:
        return list(self._users.values())

    def user(self, user_id: UUID) -> User | None:
        return self._users.get(user_id)

    def user_by_phone(self, phone: str) -> User | None:
        return next((k for k in self._users.values() if k.phone == phone), None)

    def save_user(self, user: User) -> None:
        self._users[user.id] = user

    def next_mask_counter(self) -> int:
        self._mask_counter += 1
        return self._mask_counter


def _madde(
    sira: int,
    tur: str,
    baslik: str,
    *,
    kritik: bool = False,
    foto: bool = False,
    secenekler: tuple[tuple[str, bool], ...] = (),
    alt: float | None = None,
    ust: float | None = None,
    birim: str | None = None,
) -> Item:
    return Item(
        id=sabit_id(f"madde:{baslik}"),
        order=sira,
        type=tur,  # type: ignore[arg-type]
        title=baslik,
        critical=kritik,
        photo_required=foto,
        options=tuple(ChoiceOption(etiket, gecer) for etiket, gecer in secenekler),
        min_value=alt,
        max_value=ust,
        unit=birim,
    )


EVET_HAYIR = (("Evet", True), ("Hayır", False), ("Uygun değil", True))


def _tohum_sablonlar() -> tuple[list[Template], list[TemplateVersion]]:
    """Kütüphanenin ilk şablonu: Kapanış (02-urun/07, şablon 1'in kısaltması).

    Tam 15 madde yerine temsilî 8 madde: editörün her madde türünü
    gösterebilmesi için biri her türden.
    """
    kapanis = Template(id=sabit_id("sablon:kapanis"), name="Kapanış (kafe)", category="Kapanış")
    acilis = Template(id=sabit_id("sablon:acilis"), name="Açılış", category="Açılış")

    kapanis_v1 = TemplateVersion(
        id=sabit_id("surum:kapanis:1"),
        template_id=kapanis.id,
        version_no=1,
        status="published",
        published_at=datetime(2026, 10, 1, 7, 0, tzinfo=UTC),
        sections=(
            Section(
                id=sabit_id("bolum:mutfak"),
                order=1,
                title="Mutfak",
                items=(
                    _madde(1, "instruction", "Kapanış sırası: mutfak → salon → güvenlik"),
                    _madde(2, "confirm", "Espresso makinesi geri yıkama yapıldı"),
                    _madde(3, "photo", "Kahve makinesi ve öğütücü temizlendi", foto=True),
                    _madde(
                        4,
                        "temperature",
                        "Süt dolabı sıcaklığı",
                        kritik=True,
                        alt=0,
                        ust=4,
                        birim="°C",
                    ),
                    _madde(
                        5,
                        "choice",
                        "Açık ürünler etiketlendi ve dolaba kaldırıldı",
                        secenekler=EVET_HAYIR,
                    ),
                ),
            ),
            Section(
                id=sabit_id("bolum:guvenlik"),
                order=2,
                title="Güvenlik",
                items=(
                    _madde(1, "choice", "Gaz vanası kapatıldı", kritik=True, secenekler=EVET_HAYIR),
                    _madde(2, "photo", "Kapı ve kepenk kilitlendi, alarm kuruldu", foto=True),
                    _madde(3, "text", "Devreden vardiyaya not"),
                ),
            ),
        ),
    )
    acilis_taslak = TemplateVersion(
        id=sabit_id("surum:acilis:1"),
        template_id=acilis.id,
        version_no=1,
        status="draft",
        sections=(
            Section(
                id=sabit_id("bolum:acilis-hazirlik"),
                order=1,
                title="Hazırlık",
                items=(_madde(1, "confirm", "Espresso makinesi açıldı ve ısındı"),),
            ),
        ),
    )
    return [kapanis, acilis], [kapanis_v1, acilis_taslak]


class MemoryTemplateRepository:
    """`TemplateRepository` portunun bellek içi karşılığı."""

    def __init__(self, *, seed: bool = True) -> None:
        self._templates: dict[UUID, Template] = {}
        self._versions: dict[UUID, TemplateVersion] = {}
        if seed:
            sablonlar, surumler = _tohum_sablonlar()
            for sablon in sablonlar:
                self._templates[sablon.id] = sablon
            for surum in surumler:
                self._versions[surum.id] = surum

    def templates(self) -> list[Template]:
        return list(self._templates.values())

    def template(self, template_id: UUID) -> Template | None:
        return self._templates.get(template_id)

    def save_template(self, template: Template) -> None:
        self._templates[template.id] = template

    def versions(self, template_id: UUID) -> list[TemplateVersion]:
        return [s for s in self._versions.values() if s.template_id == template_id]

    def version(self, version_id: UUID) -> TemplateVersion | None:
        return self._versions.get(version_id)

    def save_version(self, version: TemplateVersion) -> None:
        self._versions[version.id] = version


def _tohum_planlar() -> list[Plan]:
    """Kapanış listesi: her gün, kapanıştan 60 dk önce, 210 dk pencere.

    Şablon kütüphanesindeki 1. şablonun plan karşılığı (02-urun/07):
    "şube kapanış saatinden 60 dk önce başlar, pencere kapanış + 90 dk".
    """
    return [
        Plan(
            id=sabit_id("plan:kapanis"),
            name="Günlük kapanış",
            template_version_id=sabit_id("surum:kapanis:1"),
            branch_ids=(
                sabit_id("sube:KDK"),
                sabit_id("sube:USK"),
                sabit_id("sube:BSK"),
            ),
            rule=WindowRule(
                recurrence="FREQ=DAILY",
                starts_on=date(2026, 10, 1),
                anchor=Anchor("close", -60),
                duration_minutes=210,
                tolerance_minutes=0,
            ),
            assignment=Assignment(kind="anyone"),
        ).validated()
    ]


def _dun_calistirmalari(plan: Plan, bugun: date) -> list[Run]:
    """Geliştirme tohumu: dünkü çalıştırmalar sonuçlarıyla.

    Panonun istisna görünümü boş veriyle anlatılamıyor; bu üç satır
    **tohum veridir** (ADR-0003: gerçek kişi ya da müşteri verisi yok) ve
    yalnızca bellek içi adaptörde durur.
    """
    dun = bugun - timedelta(days=1)
    sonuclar: list[tuple[str, str, str | None, int | None, int]] = [
        ("sube:KDK", "submitted", "passed", 100, -20),  # zamanında
        ("sube:USK", "submitted", "failed", 86, 25),  # geç ve başarısız
        ("sube:BSK", "scheduled", None, None, 0),  # kaçırıldı (tolerans geçti)
    ]
    runs: list[Run] = []
    for kod, durum, sonuc, puan, dakika in sonuclar:
        baslangic = datetime.combine(dun, time(19, 0), tzinfo=UTC)
        bitis = baslangic + timedelta(minutes=210)
        runs.append(
            Run(
                id=sabit_id(f"calistirma:{kod}:{dun.isoformat()}"),
                plan_id=plan.id,
                template_version_id=plan.template_version_id,
                branch_id=sabit_id(kod),
                business_day=dun,
                window_start=baslangic,
                window_end=bitis,
                tolerance_end=bitis,
                status=durum,  # type: ignore[arg-type]
                result=sonuc,  # type: ignore[arg-type]
                score_percent=puan,
                submitted_at=(bitis + timedelta(minutes=dakika)) if sonuc else None,
            )
        )
    return runs


class MemoryPlanRepository:
    """`PlanRepository` portunun bellek içi karşılığı."""

    def __init__(self, *, seed: bool = True) -> None:
        self._plans: dict[UUID, Plan] = {}
        self._runs: dict[UUID, Run] = {}
        if seed:
            for plan in _tohum_planlar():
                self._plans[plan.id] = plan
            for run in _dun_calistirmalari(
                next(iter(self._plans.values())), datetime.now(UTC).date()
            ):
                self._runs[run.id] = run

    def plans(self) -> list[Plan]:
        return list(self._plans.values())

    def plan(self, plan_id: UUID) -> Plan | None:
        return self._plans.get(plan_id)

    def save_plan(self, plan: Plan) -> None:
        self._plans[plan.id] = plan

    def runs(self) -> list[Run]:
        return list(self._runs.values())

    def save_run(self, run: Run) -> None:
        self._runs[run.id] = run

    def delete_run(self, run_id: UUID) -> None:
        self._runs.pop(run_id, None)


class MemoryActionRepository:
    """`ActionRepository` portunun bellek içi karşılığı.

    Tohum yok: aksiyonlar kaçırılan çalıştırmalardan doğar (zamanlayıcı
    turu) ya da elle açılır.
    """

    def __init__(self) -> None:
        self._actions: dict[UUID, Action] = {}

    def actions(self) -> list[Action]:
        return list(self._actions.values())

    def action(self, action_id: UUID) -> Action | None:
        return self._actions.get(action_id)

    def save_action(self, action: Action) -> None:
        self._actions[action.id] = action


class MemoryEvidenceRepository:
    """`EvidenceRepository` portunun bellek içi karşılığı.

    Özete göre arama bir sözlükle: tekillik denetimi (FR-0614)
    her yüklemede koşuyor, doğrusal tarama kabul edilemez.
    """

    def __init__(self) -> None:
        self._evidences: dict[UUID, Evidence] = {}
        self._by_digest: dict[str, UUID] = {}

    def evidences(self) -> list[Evidence]:
        return list(self._evidences.values())

    def evidence(self, evidence_id: UUID) -> Evidence | None:
        return self._evidences.get(evidence_id)

    def stored_evidences(self, limit: int) -> list[Evidence]:
        return [k for k in self._evidences.values() if k.status == "stored"][:limit]

    def evidence_by_digest(self, sha256: str) -> Evidence | None:
        kimlik = self._by_digest.get(sha256)
        return self._evidences.get(kimlik) if kimlik else None

    def save_evidence(self, evidence: Evidence) -> None:
        self._evidences[evidence.id] = evidence
        self._by_digest[evidence.sha256] = evidence.id

    def delete_evidence(self, evidence_id: UUID) -> None:
        kanit = self._evidences.pop(evidence_id, None)
        if kanit is not None:
            self._by_digest.pop(kanit.sha256, None)


class MemoryNotificationRepository:
    """`NotificationRepository` portunun bellek içi karşılığı.

    Tohum yok: bildirimler zamanlayıcı turunda doğar. Süreç yeniden
    başlayınca kuyruk sıfırlanır — kalıcılık gereken her şey gibi
    teslimat izi de PostgreSQL ister.
    """

    def __init__(self) -> None:
        self._notifications: dict[UUID, Notification] = {}

    def notifications(self) -> list[Notification]:
        return list(self._notifications.values())

    def notification(self, notification_id: UUID) -> Notification | None:
        return self._notifications.get(notification_id)

    def save_notification(self, notification: Notification) -> None:
        self._notifications[notification.id] = notification


class MemoryAnswerRepository:
    """`AnswerRepository` portunun bellek içi karşılığı.

    Cevap kimliği cihazda üretildiği için anahtar doğrudan onu kullanır:
    aynı kimlikle ikinci yazma var olanı değiştirir (idempotency).
    """

    def __init__(self) -> None:
        self._answers: dict[UUID, Answer] = {}
        self._locks: dict[UUID, RunLock] = {}

    def answers(self, run_id: UUID) -> list[Answer]:
        return [a for a in self._answers.values() if a.run_id == run_id]

    def answer(self, answer_id: UUID) -> Answer | None:
        return self._answers.get(answer_id)

    def save_answer(self, answer: Answer) -> None:
        self._answers[answer.id] = answer

    def lock(self, run_id: UUID) -> RunLock | None:
        return self._locks.get(run_id)

    def save_lock(self, run_id: UUID, lock: RunLock | None) -> None:
        if lock is None:
            self._locks.pop(run_id, None)
        else:
            self._locks[run_id] = lock
