"""Kanıt servisi: yükleme izni, doğrulama, imzalı görüntüleme (ST-039, ST-049).

Akış üç çağrı (FR-0606):

1. `start` — istemci dosyanın özetini, türünü ve boyutunu bildirir.
   Sunucu tekilliği denetler (FR-0614), bayrakları hesaplar (FR-0615)
   ve **kısa ömürlü bir yükleme belirteci** verir.
2. `complete` — yükleme bitince sunucu depodaki baytların özetini
   hesaplar ve beyanla karşılaştırır. Tutmuyorsa kanıt reddedilir ve
   dosya silinir: doğrulanmamış bayt kanıt değildir.
3. `view_token` — 15 dakikalık imzalı bağlantı (FR-1305).

**Tekillik neden burada:** aynı fotoğrafı yeniden göndermek listeyi
doldurmanın en kolay yolu olurdu. Reddi kullanıcıya açık söylüyoruz
("bu fotoğraf daha önce gönderildi, yeniden çekin") ve denemeyi
günlüğe yazıyoruz — bayrak suçlama değil, kayıt tutmaktır.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog

from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.domain.evidence import (
    MAX_PER_ITEM,
    URL_TTL,
    Evidence,
    check_content_type,
    check_digest,
    check_size,
    distance_meters,
    evidence_flags,
    storage_key,
)
from talimatname.services.organization import OrganizationRepository
from talimatname.services.plans import PlanRepository
from talimatname.services.storage import ObjectMissing, ObjectStore, digest
from talimatname.services.tokens import coz, imzala
from talimatname.settings import Settings, get_settings

log = structlog.get_logger(__name__)

UPLOAD_SCOPE = "evidence-upload"
VIEW_SCOPE = "evidence-view"


class EvidenceNotFound(DomainError):
    code = "kanit-bulunamadi"
    title = "Kanıt bulunamadı"
    kind: ErrorKind = "not_found"


class DuplicateEvidence(DomainError):
    code = "kanit-tekrari"
    title = "Bu fotoğraf daha önce gönderildi, yeniden çekin"
    kind: ErrorKind = "conflict"


class TooManyEvidence(DomainError):
    code = "kanit-sayisi-asildi"
    title = f"Madde başına en çok {MAX_PER_ITEM} fotoğraf"
    kind: ErrorKind = "invalid"


class EvidenceNotStored(DomainError):
    code = "kanit-yuklenmedi"
    title = "Dosya depoya ulaşmadı"
    kind: ErrorKind = "invalid"


class DigestMismatch(DomainError):
    code = "kanit-ozeti-tutmadi"
    title = "Yüklenen dosya bildirilen özetle eşleşmiyor"
    kind: ErrorKind = "invalid"


class EvidenceRepository:
    """Kalıcılık portu. Protocol değil sınıf: bellek içi ve SQL aynı yüzey."""

    def evidences(self) -> list[Evidence]:  # pragma: no cover - arayüz
        raise NotImplementedError

    def evidence(self, evidence_id: UUID) -> Evidence | None:  # pragma: no cover
        raise NotImplementedError

    def evidence_by_digest(self, sha256: str) -> Evidence | None:  # pragma: no cover
        raise NotImplementedError

    def save_evidence(self, evidence: Evidence) -> None:  # pragma: no cover
        raise NotImplementedError

    def delete_evidence(self, evidence_id: UUID) -> None:  # pragma: no cover
        raise NotImplementedError


class EvidenceService:
    def __init__(
        self,
        repo: EvidenceRepository,
        plans: PlanRepository,
        org: OrganizationRepository,
        store: ObjectStore,
        *,
        settings: Settings | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._plans = plans
        self._org = org
        self._store = store
        self._ayar = settings or get_settings()
        self._now = now

    # --- okuma -------------------------------------------------------

    def get(self, evidence_id: UUID) -> Evidence:
        kayit = self._repo.evidence(evidence_id)
        if kayit is None:
            raise EvidenceNotFound(f"id: {evidence_id}")
        return kayit

    def for_answer(self, answer_id: UUID) -> list[Evidence]:
        return [k for k in self._repo.evidences() if k.answer_id == answer_id]

    def for_run(self, run_id: UUID) -> list[Evidence]:
        return [k for k in self._repo.evidences() if k.run_id == run_id]

    def verified_counts(self, run_id: UUID) -> dict[UUID, int]:
        """Madde başına **doğrulanmış** kanıt sayısı (FR-0607'nin dayanağı).

        Yalnızca baytları depoda olan ve özeti tutan kayıtlar sayılır.
        Niyet beyanı (`pending`) sayılmaz: cihazın "fotoğraf çektim"
        demesi, fotoğrafın var olduğu anlamına gelmiyor — çevrimdışı
        kuyrukta beyan ile dosya arasında saatler olabilir.
        """
        sayilar: dict[UUID, int] = {}
        for kanit in self.for_run(run_id):
            if kanit.status in ("stored", "stamped"):
                sayilar[kanit.item_id] = sayilar.get(kanit.item_id, 0) + 1
        return sayilar

    def find(self, evidence_id: UUID) -> Evidence | None:
        """Varsa getirir, yoksa None. Senk yolunun idempotans denetimi."""
        return self._repo.evidence(evidence_id)

    def resume(self, evidence_id: UUID) -> tuple[Evidence, str | None]:
        """Yarım kalan yüklemeyi sürdürür (FR-0707, UC-09/E3).

        Dönen belirteç `None` ise yapacak bir şey yok: baytlar zaten
        depoda ve doğrulanmış. Doğrulanmış kanıta ikinci kez yazma
        izni vermek, değişmezliği (BR-12) kendi elimizle bozmak olurdu.
        """
        kanit = self.get(evidence_id)
        if kanit.status != "pending":
            return kanit, None
        return kanit, self._yukleme_belirteci(kanit, self._now())

    # --- yazma -------------------------------------------------------

    def start(
        self,
        *,
        run_id: UUID,
        answer_id: UUID,
        item_id: UUID,
        sha256: str,
        content_type: str,
        size_bytes: int,
        user_id: UUID | None = None,
        device_id: UUID | None = None,
        from_gallery: bool = False,
        captured_at: datetime | None = None,
        device_reported_at: datetime | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        evidence_id: UUID | None = None,
        clock_skew_minutes: int | None = None,
    ) -> tuple[Evidence, str]:
        """Yükleme izni verir. Dönen: (kanıt kaydı, yükleme belirteci).

        `evidence_id` **senk yolundan** gelir (ST-054, FR-0707): kimliği
        cihaz ürettiği için aynı fotoğraf iki kez gönderilse de tek
        kayıt olur. `clock_skew_minutes` de senk anında ölçülen farktır;
        kuyruktaki kaydın cihaz zamanından türetilemez.
        """
        an = self._now()
        ozet = check_digest(sha256)
        tur = check_content_type(content_type)
        boyut = check_size(size_bytes)

        run = next((r for r in self._plans.runs() if r.id == run_id), None)
        if run is None:
            raise EvidenceNotFound(f"çalıştırma: {run_id}")

        # Tekillik (FR-0614): aynı özet hesapta ikinci kez kullanılamaz.
        ayni = self._repo.evidence_by_digest(ozet)
        if ayni is not None:
            log.warning(
                "kanit.tekrar_denemesi",
                sha256=ozet,
                calistirma=str(run_id),
                onceki=str(ayni.id),
                kullanici=str(user_id) if user_id else None,
            )
            raise DuplicateEvidence(f"Aynı dosya daha önce yüklendi: {ayni.id}")

        if len([k for k in self.for_answer(answer_id) if k.item_id == item_id]) >= MAX_PER_ITEM:
            raise TooManyEvidence(f"madde: {item_id}")

        sube = self._org.branch(run.branch_id)
        sapma = (
            clock_skew_minutes
            if clock_skew_minutes is not None
            else (
                round((device_reported_at - an).total_seconds() / 60)
                if device_reported_at is not None
                else None
            )
        )
        bayraklar = evidence_flags(
            from_gallery=from_gallery,
            latitude=latitude,
            longitude=longitude,
            branch_latitude=sube.latitude if sube else None,
            branch_longitude=sube.longitude if sube else None,
            clock_skew_minutes=sapma,
            captured_at=captured_at,
            received_at=an,
        )
        uzaklik = (
            round(distance_meters(latitude, longitude, sube.latitude, sube.longitude))
            if sube is not None
            and sube.latitude is not None
            and sube.longitude is not None
            and latitude is not None
            and longitude is not None
            else None
        )

        kanit_id = evidence_id or uuid4()
        kanit = Evidence(
            id=kanit_id,
            run_id=run_id,
            answer_id=answer_id,
            item_id=item_id,
            branch_id=run.branch_id,
            user_id=user_id,
            sha256=ozet,
            content_type=tur,
            size_bytes=boyut,
            storage_key=storage_key(run_id, kanit_id, tur),
            created_at=an,
            captured_at=captured_at,
            device_reported_at=device_reported_at,
            clock_skew_minutes=sapma,
            latitude=latitude,
            longitude=longitude,
            distance_meters=uzaklik,
            device_id=device_id,
            from_gallery=from_gallery,
            flags=bayraklar,
        ).validated()
        self._repo.save_evidence(kanit)
        return kanit, self._yukleme_belirteci(kanit, an)

    def receive(self, token: str, data: bytes) -> Evidence:
        """Yerel adaptörde baytları alır. S3'te bu adım kovaya gider."""
        govde = coz(self._ayar, token, scope=UPLOAD_SCOPE)
        kanit = self.get(UUID(govde["sub"]))
        self._store.put(kanit.storage_key, data)
        return kanit

    def complete(self, evidence_id: UUID) -> Evidence:
        """Depodaki baytları doğrular. Tutmuyorsa kanıt reddedilir."""
        kanit = self.get(evidence_id)
        an = self._now()
        try:
            baytlar = self._store.get(kanit.storage_key)
        except ObjectMissing as hata:
            raise EvidenceNotStored(f"anahtar: {kanit.storage_key}") from hata

        gercek = digest(baytlar)
        if gercek != kanit.sha256:
            log.warning(
                "kanit.ozet_tutmadi",
                kanit=str(kanit.id),
                beyan=kanit.sha256,
                gercek=gercek,
            )
            # Kayıt **silinir**, bastırılmaz: doğrulanmamış bayt kanıt
            # değildir ve tekillik kilidini (FR-0614) tutmamalı —
            # yoksa kullanıcı aynı kareyi bir daha yükleyemezdi.
            # Denemenin kendisi yukarıdaki günlük satırında duruyor.
            self._store.delete(kanit.storage_key)
            self._repo.delete_evidence(kanit.id)
            raise DigestMismatch(f"beyan {kanit.sha256[:12]}…, gerçek {gercek[:12]}…")

        tamam = kanit.stored(an)
        self._repo.save_evidence(tamam)
        return tamam

    # --- bağlantılar ---------------------------------------------------

    def _yukleme_belirteci(self, kanit: Evidence, an: datetime) -> str:
        return imzala(
            self._ayar,
            subject=str(kanit.id),
            scope=UPLOAD_SCOPE,
            ttl=URL_TTL,
            now=an,
        )

    def view_token(self, evidence_id: UUID) -> str:
        """15 dakikalık imzalı görüntüleme belirteci (FR-1305)."""
        kanit = self.get(evidence_id)
        return imzala(
            self._ayar,
            subject=str(kanit.id),
            scope=VIEW_SCOPE,
            ttl=URL_TTL,
            now=self._now(),
        )

    def read(self, token: str) -> tuple[Evidence, bytes]:
        govde = coz(self._ayar, token, scope=VIEW_SCOPE)
        kanit = self.get(UUID(govde["sub"]))
        try:
            return kanit, self._store.get(kanit.storage_key)
        except ObjectMissing as hata:
            raise EvidenceNotStored(f"anahtar: {kanit.storage_key}") from hata
