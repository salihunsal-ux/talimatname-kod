"""Çalıştırma yürütme uç noktaları (ST-030, ST-033; FR-0602, FR-0607, FR-0521).

Mobilin bağlanacağı yüzey. Cevabın kimliği **cihazda** üretilir ve
yoldadır (`PUT .../answers/{answer_id}`): çevrimdışı kuyruk aynı cevabı
birden çok kez gönderse de tek kayıt oluşur (ADR-0013 devir sözleşmesi).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from talimatname.api.bagimliliklar import (
    disa_aktarim_servisi,
    izi_servisi,
    kurulum_servisi,
    marka,
    organizasyon_servisi,
    sablon_servisi,
    yurutme_servisi,
)
from talimatname.api.guvenlik import Kullanici, sube_erisimi_zorunlu
from talimatname.domain.sync import NOT_DONE_REASON_LABELS
from talimatname.domain.templates import ITEM_TYPE_LABELS
from talimatname.services.audit import AuditService
from talimatname.services.execution import ExecutionService, RunView
from talimatname.services.exports import ExportService, pdf_filename, record_document
from talimatname.services.organization import OrganizationService
from talimatname.services.pdf import run_code, run_pdf
from talimatname.services.setup import SetupService
from talimatname.services.templates import TemplateService

router = APIRouter(tags=["yürütme"])

Servis = Annotated[ExecutionService, Depends(yurutme_servisi)]
SablonServis = Annotated[TemplateService, Depends(sablon_servisi)]
OrgServis = Annotated[OrganizationService, Depends(organizasyon_servisi)]
DisaAktarim = Annotated[ExportService, Depends(disa_aktarim_servisi)]
KurulumServis = Annotated[SetupService, Depends(kurulum_servisi)]
Iz = Annotated[AuditService, Depends(izi_servisi)]


NotDoneSebebi = Literal["no_material", "equipment_broken", "no_time", "not_authorized", "other"]


class CevapGirdisi(BaseModel):
    item_id: UUID
    state: Literal["passed", "failed", "not_done", "not_applicable"]
    value: Any = None
    note: str | None = None
    user_id: UUID | None = None
    device_id: UUID | None = None
    device_reported_at: datetime | None = Field(
        default=None,
        description="Cihazın saati. Kaydedilir ama karar için kullanılmaz (BR-13).",
    )
    evidence_count: int = Field(default=0, ge=0, le=3)
    not_done_reason: NotDoneSebebi | None = Field(
        default=None, description="Yapılamadı sebebi; 'yapılamadı' ile zorunlu (BR-09)"
    )


class CevapCiktisi(BaseModel):
    id: UUID
    item_id: UUID
    state: str
    value: Any = None
    note: str | None = None
    evidence_count: int
    answered_at: datetime | None
    clock_skew_minutes: int | None = None
    clock_flagged: bool = False
    not_done_reason: str | None = None
    not_done_reason_label: str | None = Field(
        default=None, description="Sebebin Türkçe karşılığı; kod sözleşme, etiket değişebilir"
    )


class MaddeDurumu(BaseModel):
    item_id: UUID
    title: str
    type: str
    type_label: str
    required: bool
    photo_required: bool
    critical: bool
    min_value: float | None = None
    max_value: float | None = None
    unit: str | None = None
    answer: CevapCiktisi | None = None


class Eksik(BaseModel):
    item_id: UUID
    title: str
    kind: Literal["unanswered", "evidence", "note"]


class CalistirmaGorunumu(BaseModel):
    run_id: UUID
    branch_id: UUID
    business_day: str
    status: str
    result: str | None = None
    score_percent: int | None = None
    window_start: datetime
    window_end: datetime
    tolerance_end: datetime
    submitted_at: datetime | None = None
    template_name: str
    locked_by: UUID | None = None
    sections: list[BolumDurumu]
    blockers: list[Eksik]


class BolumDurumu(BaseModel):
    id: UUID
    title: str
    items: list[MaddeDurumu]


def _sebep_etiketi(kod: str | None) -> str | None:
    return NOT_DONE_REASON_LABELS[kod] if kod else None  # type: ignore[index]


def _cevap(gorunum: RunView, item_id: UUID) -> CevapCiktisi | None:
    cevap = gorunum.answers.get(item_id)
    if cevap is None:
        return None
    return CevapCiktisi(
        id=cevap.id,
        item_id=cevap.item_id,
        state=cevap.state,
        value=cevap.value,
        note=cevap.note,
        evidence_count=cevap.evidence_count,
        answered_at=cevap.answered_at,
        clock_skew_minutes=cevap.clock_skew_minutes,
        clock_flagged=cevap.clock_flagged,
        not_done_reason=cevap.not_done_reason,
        not_done_reason_label=_sebep_etiketi(cevap.not_done_reason),
    )


def _gorunum(gorunum: RunView, template_name: str) -> CalistirmaGorunumu:
    run = gorunum.run
    return CalistirmaGorunumu(
        run_id=run.id,
        branch_id=run.branch_id,
        business_day=run.business_day.isoformat(),
        status=run.status,
        result=run.result,
        score_percent=run.score_percent,
        window_start=run.window_start,
        window_end=run.window_end,
        tolerance_end=run.tolerance_end,
        submitted_at=run.submitted_at,
        template_name=template_name,
        locked_by=gorunum.lock.user_id if gorunum.lock else None,
        sections=[
            BolumDurumu(
                id=bolum.id,
                title=bolum.title,
                items=[
                    MaddeDurumu(
                        item_id=madde.id,
                        title=madde.title,
                        type=madde.type,
                        type_label=ITEM_TYPE_LABELS[madde.type],
                        required=madde.required,
                        photo_required=madde.photo_required,
                        critical=madde.critical,
                        min_value=madde.min_value,
                        max_value=madde.max_value,
                        unit=madde.unit,
                        answer=_cevap(gorunum, madde.id),
                    )
                    for madde in bolum.items
                ],
            )
            for bolum in gorunum.version.sections
        ],
        blockers=[Eksik(item_id=e.item_id, title=e.title, kind=e.kind) for e in gorunum.blockers],
    )


@router.get("/runs/{run_id}", summary="Çalıştırma görünümü (maddeler ve cevaplar)")
def calistirma_gorunumu(
    run_id: UUID,
    servis: Servis,
    sablonlar: SablonServis,
    org: OrgServis,
    kullanici: Kullanici,
) -> CalistirmaGorunumu:
    gorunum = servis.view(run_id)
    sube_erisimi_zorunlu(kullanici, gorunum.run.branch_id, org)
    return _gorunum(gorunum, sablonlar.get(gorunum.version.template_id).name)


@router.put("/runs/{run_id}/answers/{answer_id}", summary="Cevap yaz (idempotent)")
def cevap_yaz(
    run_id: UUID,
    answer_id: UUID,
    girdi: CevapGirdisi,
    servis: Servis,
    org: OrgServis,
    kullanici: Kullanici,
) -> CevapCiktisi:
    """Aynı `answer_id` ile ikinci çağrı yeni kayıt açmaz, var olanı günceller.

    Cevabı yazan **oturumdaki kullanıcıdır**: gövdedeki `user_id` artık
    dikkate alınmıyor. Kapsam dışı şubenin çalıştırmasına yazılamaz.
    """
    sube_erisimi_zorunlu(kullanici, servis.view(run_id).run.branch_id, org)
    cevap = servis.write_answer(
        run_id=run_id,
        answer_id=answer_id,
        item_id=girdi.item_id,
        state=girdi.state,
        value=girdi.value,
        note=girdi.note,
        user_id=kullanici.id,
        device_id=girdi.device_id,
        device_reported_at=girdi.device_reported_at,
        evidence_count=girdi.evidence_count,
        not_done_reason=girdi.not_done_reason,
    )
    return CevapCiktisi(
        id=cevap.id,
        item_id=cevap.item_id,
        state=cevap.state,
        value=cevap.value,
        note=cevap.note,
        evidence_count=cevap.evidence_count,
        answered_at=cevap.answered_at,
        clock_skew_minutes=cevap.clock_skew_minutes,
        clock_flagged=cevap.clock_flagged,
        not_done_reason=cevap.not_done_reason,
        not_done_reason_label=_sebep_etiketi(cevap.not_done_reason),
    )


class GonderimGirdisi(BaseModel):
    user_id: UUID | None = None


@router.post("/runs/{run_id}/submit", summary="Listeyi gönder")
def calistirma_gonder(
    run_id: UUID,
    girdi: GonderimGirdisi,
    servis: Servis,
    sablonlar: SablonServis,
    org: OrgServis,
    kullanici: Kullanici,
) -> CalistirmaGorunumu:
    """Eksik varsa 422 ve eksiklerin listesi döner; puan sunucuda hesaplanır.

    Gönderen de oturumdaki kullanıcıdır (gövdedeki `user_id` yok sayılır).
    """
    sube_erisimi_zorunlu(kullanici, servis.view(run_id).run.branch_id, org)
    servis.submit(run_id, user_id=kullanici.id)
    gorunum = servis.view(run_id)
    return _gorunum(gorunum, sablonlar.get(gorunum.version.template_id).name)


@router.get(
    "/runs/{run_id}/pdf",
    summary="Çalıştırma PDF'i (FR-1213)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "PDF"}},
)
def calistirma_pdf(
    run_id: UUID,
    servis: Servis,
    disa: DisaAktarim,
    kurulum: KurulumServis,
    iz: Iz,
    org: OrgServis,
    kullanici: Kullanici,
) -> Response:
    """Denetçinin eline verilen kâğıt: maddeler, cevaplar, kanıt, iz.

    Kapsam denetimi ekranla **aynı**: şubesini göremeyen kullanıcı
    kâğıdını da alamaz. PDF ayrı bir kapı açsaydı, en çok veri taşıyan
    çıktı en zayıf kapıdan geçerdi.
    """
    gorunum = servis.view(run_id)
    sube_erisimi_zorunlu(kullanici, gorunum.run.branch_id, org)

    rapor = disa.run_report(run_id)
    hesap = marka()
    kod = record_document(
        iz,
        tur="calistirma",
        icerik_kodu=run_code(rapor, brand=hesap),
        donem=f"{rapor.business_day:%Y-%m-%d}",
        sube=rapor.branch_code,
        nesne_turu="calistirma",
        nesne_id=run_id,
    )
    icerik = run_pdf(
        rapor,
        brand=hesap,
        generated_at=datetime.now(UTC),
        generated_by=kullanici.full_name,
        code=kod,
    )
    return Response(
        content=icerik,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{pdf_filename(rapor)}"'},
    )
