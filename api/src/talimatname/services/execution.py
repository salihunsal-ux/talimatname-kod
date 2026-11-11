"""Çalıştırma yürütme: cevap yazma ve gönderim (ST-030, ST-033, ST-139).

Mobilin bağlanacağı yüzey burası. Üç davranış sözleşme sayılır ve
Faz B'den önce değişmemeli (ADR-0013 devir kapısı):

1. `PUT .../answers/{uuid}` **idempotent**: aynı gövdeyle tekrar aynı
   kaydı verir, farklı gövdeyle son yazan kazanır.
2. Gönderim **eksik varken reddedilir** ve eksiklerin listesini döner
   (FR-0607); puan ve sonuç sunucuda hesaplanır (FR-0306/0307).
3. Kilit: "biri tamamlasın" listesinde ilk açan alır (FR-0521).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from talimatname.domain.actions import from_critical_item, from_failed_item, from_not_done
from talimatname.domain.answers import (
    Answer,
    Missing,
    RunLock,
    clock_skew,
    ensure_writable,
    outcomes,
    resolve_answer,
    submission_blockers,
)
from talimatname.domain.errors import DomainError, ErrorKind, RunLocked
from talimatname.domain.plans import RUN_STATUS_LABELS, Run
from talimatname.domain.scoring import evaluate
from talimatname.domain.sync import NOT_DONE_REASON_LABELS
from talimatname.domain.templates import Item, TemplateVersion
from talimatname.domain.validation import ValidationError
from talimatname.services.actions import ActionRepository
from talimatname.services.audit import AuditService
from talimatname.services.plans import PlanRepository
from talimatname.services.templates import TemplateRepository


class RunNotFound(DomainError):
    code = "calistirma-bulunamadi"
    title = "Çalıştırma bulunamadı"
    kind: ErrorKind = "not_found"


class RunClosed(DomainError):
    code = "calistirma-kapali"
    title = "Bu çalıştırma gönderilmiş ya da iptal edilmiş"
    kind: ErrorKind = "conflict"


class RunNotCancellable(DomainError):
    code = "calistirma-iptal-edilemez"
    title = "Bu çalıştırma yapılmayacak yapılamaz"
    kind: ErrorKind = "conflict"


class WindowClosed(DomainError):
    code = "pencere-kapali"
    title = "Pencere ve tolerans süresi doldu"
    kind: ErrorKind = "conflict"


class WindowNotOpen(DomainError):
    """Pencere henüz açılmadı (hazırlık payı dahil).

    Üst sınır gibi bu da kesin: liste penceresinden önce doldurulabilseydi
    \"pencere içi tamamlandı\" ölçüsü (FR-1203) ölçtüğünü iddia ettiği
    şeyi ölçmezdi.
    """

    code = "pencere-acilmadi"
    title = "Pencere henüz açılmadı"
    kind: ErrorKind = "conflict"


class ItemNotInTemplate(DomainError):
    code = "madde-bulunamadi"
    title = "Madde bu şablon sürümünde yok"
    kind: ErrorKind = "not_found"


class NotDoneNotAllowed(DomainError):
    code = "kritik-maddede-yapilamadi-yok"
    title = "Kritik maddede 'yapılamadı' seçilemez"
    kind: ErrorKind = "invalid"


class SubmissionIncomplete(DomainError):
    code = "gonderim-eksik"
    title = "Liste eksik: gönderilemez"
    kind: ErrorKind = "invalid"


class AnswerRepository(Protocol):
    def answers(self, run_id: UUID) -> list[Answer]: ...

    def answers_for_runs(self, run_ids: list[UUID]) -> dict[UUID, list[Answer]]:
        """Rapor yolu: çalıştırma başına ayrı sorgu bir ayda 200 gidiş-dönüş."""
        ...

    def answer(self, answer_id: UUID) -> Answer | None: ...

    def save_answer(self, answer: Answer) -> None: ...

    def lock(self, run_id: UUID) -> RunLock | None: ...

    def save_lock(self, run_id: UUID, lock: RunLock | None) -> None: ...


@dataclass(frozen=True, slots=True)
class RunView:
    """Çalıştırma + şablon + cevaplar: ekranın ve gönderimin ortak görünümü."""

    run: Run
    version: TemplateVersion
    answers: dict[UUID, Answer]
    lock: RunLock | None
    blockers: list[Missing]


class ExecutionService:
    def __init__(
        self,
        answers: AnswerRepository,
        plans: PlanRepository,
        templates: TemplateRepository,
        actions: ActionRepository | None = None,
        *,
        verified_evidence: Callable[[UUID], dict[UUID, int]] | None = None,
        user_name: Callable[[UUID], str | None] | None = None,
        audit: AuditService | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        prep_minutes: int = 0,
    ) -> None:
        self._answers = answers
        self._plans = plans
        self._templates = templates
        self._actions = actions
        self._verified = verified_evidence
        #: Kilidi kimin tuttuğunu **adıyla** söyleyebilmek için (BR-26:
        #: "diğerleri X yapıyor görür"). Ham kimlik kullanıcıya bir şey
        #: anlatmıyordu: "Kilit sahibi: 73a8e2ba-…" diyordu.
        self._isim = user_name
        #: Olay günlüğü isteğe bağlı: alan testleri zincir kurmadan
        #: yürütme servisini kullanabilsin (FR-1301).
        self._izi = audit
        self._now = now
        #: Pencere açılmadan önce yazmaya izin verilen pay (BR-02). Alan
        #: testleri payı vermiyor: varsayılan 0, yani tam pencerede açılır.
        self._prep_minutes = prep_minutes

    @property
    def prep_minutes(self) -> int:
        """Hazırlık payı; senk manifesti de aynı değeri kullanmalı."""
        return self._prep_minutes

    # --- okuma -------------------------------------------------------

    def view(self, run_id: UUID) -> RunView:
        run = self._run(run_id)
        surum = self._version(run)
        cevaplar = self._cevaplar(run_id)
        return RunView(
            run=run,
            version=surum,
            answers=cevaplar,
            lock=self._answers.lock(run_id),
            blockers=submission_blockers(items=self._items(surum), answers=cevaplar),
        )

    # --- yazma -------------------------------------------------------

    def write_answer(
        self,
        *,
        run_id: UUID,
        answer_id: UUID,
        item_id: UUID,
        state: str,
        value: object = None,
        note: str | None = None,
        user_id: UUID | None = None,
        device_id: UUID | None = None,
        device_reported_at: datetime | None = None,
        evidence_count: int = 0,
        not_done_reason: str | None = None,
        clock_skew_minutes: int | None = None,
    ) -> Answer:
        """Cevabı yazar (idempotent). Kimlik cihazdan gelir.

        `clock_skew_minutes` **yalnızca senk yolundan** dolu gelir
        (ST-054): kuyruktaki bir cevabın cihaz zamanı geçmişte olduğu
        için sapma o değerden türetilemez — türetilse saatler sapma
        gösterirdi. Senk anında ölçülen fark buradan geçirilir.
        """
        an = self._now()
        run = self._run(run_id)
        self._ensure_open(run, an)
        surum = self._version(run)
        madde = next((m for m in surum.items if m.id == item_id), None)
        if madde is None:
            raise ItemNotInTemplate(f"Madde id: {item_id}")
        if madde.critical and state == "not_done":
            # BR-09: kritik madde atlanamaz, sebebi de olmaz.
            raise NotDoneNotAllowed(f"Madde: {madde.title}")

        # BR-06: sonucu sunucu hesaplar. Kilitten **önce**: bozuk bir
        # istek kimsenin kilidini tazelemesin.
        durum, deger = resolve_answer(madde, state=state, value=value)

        kilit = self._kilidi_dogrula(run_id, user_id, an)
        self._answers.save_lock(run_id, kilit)

        cevap = Answer(
            id=answer_id,
            run_id=run_id,
            item_id=item_id,
            state=durum,
            value=deger,
            note=note,
            user_id=user_id,
            device_id=device_id,
            answered_at=an,
            device_reported_at=device_reported_at,
            clock_skew_minutes=(
                clock_skew_minutes
                if clock_skew_minutes is not None
                else clock_skew(an, device_reported_at)
            ),
            evidence_count=evidence_count,
            not_done_reason=not_done_reason,  # type: ignore[arg-type]
        ).validated()
        self._answers.save_answer(cevap)
        self._cevap_aksiyonu(run, madde, cevap, an)

        if run.status == "scheduled":
            self._plans.save_run(replace(run, status="in_progress"))
        return cevap

    def submit(self, run_id: UUID, *, user_id: UUID | None = None) -> Run:
        """Listeyi gönderir: eksikleri denetler, puanı ve sonucu hesaplar."""
        an = self._now()
        run = self._run(run_id)
        self._ensure_open(run, an)
        # BR-26: kilit yazmada denetleniyordu, gönderimde değil. Listeyi
        # A dolduruyorken B gönderebiliyor ve `locked_by` B'ye yazıldığı
        # için kayıt işi B'ye atfediyordu (bağımsız test turu B03).
        # Kilidi tazelemeye gerek yok: gönderim onu zaten düşürüyor.
        self._kilidi_dogrula(run_id, user_id, an)
        surum = self._version(run)
        cevaplar = self._cevaplar(run_id)

        eksikler = submission_blockers(items=self._items(surum), answers=cevaplar)
        if eksikler:
            raise SubmissionIncomplete(
                f"{len(eksikler)} madde eksik",
                missing=[
                    {"item_id": str(m.item_id), "title": m.title, "kind": m.kind} for m in eksikler
                ],
            )

        meta = {madde.id: (madde.critical, madde.scored) for madde in surum.items}
        degerlendirme = evaluate(outcomes(list(cevaplar.values()), meta))

        gonderilen = replace(
            run,
            status="submitted",
            result=degerlendirme.result,
            score_percent=degerlendirme.score_percent,
            submitted_at=an,
            locked_by=user_id,
        )
        self._plans.save_run(gonderilen)
        self._answers.save_lock(run_id, None)
        self._kritik_aksiyonlar(run, surum, degerlendirme.failed_critical_items, an)
        if self._izi is not None:
            self._izi.record(
                "calistirma.gonderildi",
                object_type="calistirma",
                object_id=run_id,
                before={"durum": run.status},
                after={
                    "durum": "submitted",
                    "sonuc": degerlendirme.result,
                    "puan": str(degerlendirme.score_percent),
                    "basarisiz_kritik": str(len(degerlendirme.failed_critical_items)),
                },
            )
        return gonderilen

    def cancel(self, run_id: UUID, *, reason: str, user_id: UUID | None = None) -> Run:
        """Çalıştırmayı "yapılmayacak" yapar (FR-0514).

        Sebep **zorunlu**: iptal edilen bir liste, denetimde kaçırılmış
        listeden ayırt edilemezse ikisi de aynı şüpheyi doğurur. Sebep
        hem kayıtta hem olay günlüğünde duruyor.

        Yalnızca "Planlandı" ve "Devam ediyor" iptal edilebilir:
        gönderilmiş bir listeyi iptal etmek kanıtı geçersiz kılmak,
        kaçırılmışı iptal etmek ise geçmişi düzeltmek olurdu.
        """
        temiz = reason.strip()
        if not temiz:
            raise ValidationError("reason", "İptal sebebi yazılmalı")

        run = self._run(run_id)
        if run.status not in ("scheduled", "in_progress"):
            raise RunNotCancellable(f"Durum: {RUN_STATUS_LABELS[run.status]}")

        iptal = replace(run, status="cancelled", cancel_reason=temiz, locked_by=user_id)
        self._plans.save_run(iptal)
        self._answers.save_lock(run_id, None)
        if self._izi is not None:
            self._izi.record(
                "calistirma.yapilmayacak",
                object_type="calistirma",
                object_id=run_id,
                before={"durum": run.status},
                after={"durum": "cancelled", "sebep": temiz},
            )
        return iptal

    def _cevap_aksiyonu(self, run: Run, madde: Item, cevap: Answer, an: datetime) -> None:
        """Cevap **kayda girer girmez** doğan aksiyonlar (FR-0405, BR-10).

        Aksiyon yalnızca gönderimde açılıyordu: 9 derecelik buzdolabı
        kaydedildikten sonra liste gönderilene kadar — kimi zaman hiç
        gönderilmeden — merkezde kimse haberdar olmuyordu. FR-1008
        'anında' diyor, FR-0405 tetik olarak **cevabı** gösteriyor
        (bağımsız test turu B04, B05).

        Kimlik (çalıştırma, madde) ikilisinden türediği için cevap
        düzeltilip yeniden yazılsa da ikinci aksiyon doğmaz; gönderim
        aşamasındaki tarama da aynı kimliği üretir. Düzeltilen cevap
        aksiyonu **geri almaz**: 9 derece ölçülmüş olması bir olaydır,
        aksiyon notuyla kapanır (BR-10).
        """
        if self._actions is None:
            return
        plan = self._plans.plan(run.plan_id)
        plan_adi = plan.name if plan else "Liste"
        if madde.critical and cevap.state == "failed":
            aksiyon = from_critical_item(
                run_id=run.id,
                item_id=madde.id,
                branch_id=run.branch_id,
                item_title=madde.title,
                plan_name=plan_adi,
                now=an,
            )
        elif madde.opens_action_on_fail and cevap.state == "failed":
            # Kritik olmayan ama şablonda takip işaretli madde (BR-10).
            # Olmadığında bulgu kayda geçip kimseye gitmiyordu: BR-07
            # gereği çalıştırmayı da başarısız yapmıyor, yani panoda da
            # görünmüyordu (8 Kasım denetim turu).
            assert madde.action_priority is not None
            aksiyon = from_failed_item(
                run_id=run.id,
                item_id=madde.id,
                branch_id=run.branch_id,
                item_title=madde.title,
                plan_name=plan_adi,
                priority=madde.action_priority,
                now=an,
            )
        elif cevap.state == "not_done":
            aksiyon = from_not_done(
                run_id=run.id,
                item_id=madde.id,
                branch_id=run.branch_id,
                item_title=madde.title,
                plan_name=plan_adi,
                reason_label=(
                    NOT_DONE_REASON_LABELS[cevap.not_done_reason] if cevap.not_done_reason else None
                ),
                now=an,
            )
        else:
            return
        if aksiyon.id not in {a.id for a in self._actions.actions()}:
            self._actions.save_action(aksiyon)

    def _kritik_aksiyonlar(
        self,
        run: Run,
        surum: TemplateVersion,
        basarisiz: tuple[str, ...],
        an: datetime,
    ) -> None:
        """Başarısız her kritik madde için aksiyon açar (FR-0405, BR-08).

        Kimlik (çalıştırma, madde) ikilisinden türediği için aynı
        liste yeniden gönderilse de ikinci aksiyon doğmaz; çevrimdışı
        senk yolu (ST-054) da bu metottan geçecek.
        """
        if self._actions is None or not basarisiz:
            return
        plan = self._plans.plan(run.plan_id)
        basliklar = {str(m.id): m.title for m in surum.items}
        mevcut = {a.id for a in self._actions.actions()}
        for madde_id in basarisiz:
            aksiyon = from_critical_item(
                run_id=run.id,
                item_id=UUID(madde_id),
                branch_id=run.branch_id,
                item_title=basliklar.get(madde_id, "Madde"),
                plan_name=plan.name if plan else "Liste",
                now=an,
            )
            if aksiyon.id not in mevcut:
                self._actions.save_action(aksiyon)

    # --- yardımcılar --------------------------------------------------

    def _cevaplar(self, run_id: UUID) -> dict[UUID, Answer]:
        """Cevaplar, kanıt sayısı **doğrulanmış** hale getirilerek.

        Cevaptaki `evidence_count` cihazın beyanıdır; gönderimi ona
        bakarak açmak, "fotoğraf var" iddiasını istemciye bırakmak
        olurdu — çevrimdışı yolda beyan dosyadan saatler önce gelir
        (ST-054). Depoda doğrulanmış kanıt varsa onun sayısı geçer.
        """
        cevaplar = {a.item_id: a for a in self._answers.answers(run_id)}
        if self._verified is None:
            return cevaplar
        dogrulanmis = self._verified(run_id)
        return {
            madde: replace(cevap, evidence_count=dogrulanmis.get(madde, 0))
            for madde, cevap in cevaplar.items()
        }

    def _kilit_izi(
        self,
        tur: str,
        run_id: UUID,
        *,
        before: dict[str, object] | None = None,
        after: dict[str, object] | None = None,
    ) -> None:
        """Kilit olayları günlüğe yazılır (BR-26 son cümle)."""
        if self._izi is None:
            return
        self._izi.record(
            tur, object_type="calistirma", object_id=run_id, before=before, after=after
        )

    def kilit_sahibi(self, run_id: UUID) -> str | None:
        """Kilidi tutanın adı; kilit yoksa, düşmüşse ya da isim yoksa None."""
        kilit = self._answers.lock(run_id)
        if kilit is None or kilit.expired(self._now()) or self._isim is None:
            return None
        return self._isim(kilit.user_id)

    def _kilidi_dogrula(self, run_id: UUID, user_id: UUID | None, an: datetime) -> RunLock | None:
        """`ensure_writable`, hatayı kilit sahibinin **adıyla** zenginleştirir.

        Alan katmanı isim bilmiyor ve bilmemeli; "X yapıyor" cümlesini
        kurabilmek (BR-26) sunum katmanının işi ama isim çözümü burada,
        çünkü hatayı doğuran yer burası.
        """
        try:
            return ensure_writable(self._answers.lock(run_id), user_id, an)
        except RunLocked as hata:
            isim = self.kilit_sahibi(run_id)
            if isim is None:
                raise
            raise RunLocked(
                f"Listeyi şu an {isim} dolduruyor",
                holder=hata.extra.get("holder"),
                holder_name=isim,
            ) from hata

    def claim(self, run_id: UUID, user_id: UUID) -> RunLock:
        """Listeyi üstlenir (BR-26: ilk açan alır).

        Yazmak kilidi zaten alıyor; bu uç nokta açık niyet için:
        personel listeyi açtığında kilidi alsın ki ikinci kişi ilk
        maddeyi yazana kadar beklemesin.
        """
        an = self._now()
        run = self._run(run_id)
        self._ensure_open(run, an)
        kilit = self._kilidi_dogrula(run_id, user_id, an)
        self._answers.save_lock(run_id, kilit)
        self._kilit_izi("calistirma.kilit_alindi", run_id, after={"kullanici": str(user_id)})
        assert kilit is not None
        return kilit

    def release(self, run_id: UUID, user_id: UUID, *, force: bool = False) -> None:
        """Kilidi bırakır. `force`: şube müdürü başkasının kilidini kaldırır.

        BR-26: "sahibi bırakırsa serbest kalır; şube müdürü kilidi
        kaldırabilir". Zorlama ayrı bir olay türüyle günlüğe giriyor:
        birinin işini devralmak, kendi işini bırakmaktan başka bir şey.
        """
        kilit = self._answers.lock(run_id)
        if kilit is None:
            return
        kendi = kilit.user_id == user_id
        if not kendi and not force:
            isim = self.kilit_sahibi(run_id)
            raise RunLocked(
                f"Listeyi şu an {isim} dolduruyor" if isim else f"Kilit sahibi: {kilit.user_id}",
                holder=str(kilit.user_id),
                holder_name=isim,
            )
        self._answers.save_lock(run_id, None)
        self._kilit_izi(
            "calistirma.kilit_birakildi" if kendi else "calistirma.kilit_kaldirildi",
            run_id,
            before={"kilit_sahibi": str(kilit.user_id)},
            after={"kullanici": str(user_id)},
        )

    def _run(self, run_id: UUID) -> Run:
        run = self._plans.run(run_id)
        if run is None:
            raise RunNotFound(f"Çalıştırma id: {run_id}")
        return run

    def _version(self, run: Run) -> TemplateVersion:
        surum = self._templates.version(run.template_version_id)
        if surum is None:
            raise RunNotFound(f"Şablon sürümü: {run.template_version_id}")
        return surum

    def _ensure_open(self, run: Run, now: datetime) -> None:
        if run.status in ("submitted", "cancelled"):
            raise RunClosed(f"Durum: {run.status}")
        acilis = run.writable_from(self._prep_minutes)
        if now < acilis:
            # Pencere daha açılmadı: hazırlık payından da önce.
            raise WindowNotOpen(f"Açılış: {acilis.isoformat()}")
        if now >= run.tolerance_end:
            # Tolerans bittiyse yazma da gönderim de kapanır (BR-03).
            raise WindowClosed(f"Tolerans bitişi: {run.tolerance_end.isoformat()}")

    @staticmethod
    def _items(surum: TemplateVersion) -> list[tuple[UUID, str, bool, bool, bool]]:
        return [
            (madde.id, madde.title, madde.required, madde.photo_required, madde.scored)
            for madde in surum.items
            if madde.scored  # talimat satırı cevaplanmaz
        ]
