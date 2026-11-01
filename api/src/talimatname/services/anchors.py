"""Zincir kökünün günlük çıpalanması (ST-103; FR-1302).

Zincirin sınırı tek cümleydi: veritabanına yazabilen biri her şeyi
baştan hesaplarsa fark edilmez. Bu modül o sınırı kaldırıyor — günün
kökü dışarıdaki bir otoriteye tarihletiliyor ve damga saklanıyor.

Üç karar:

**Otorite bir port.** Servis HTTP bilmez (ADR-0014 md.2; `requests`
bu katmanda yasak): `TimestampAuthority` arayüzü var, RFC 3161
istemcisi `infra/tsa.py`de. Testler gerçek bir damga üreten sahte
otoriteyle koşuyor, ağa çıkmadan.

**Başarısızlık kayda geçer.** Damga alınamazsa `failed` durumlu bir
satır yazılıyor. Çıpasız bir gün çıpalı sanılmasın: denetimde
"o gün neden yok" sorusunun cevabı kayıtta dursun. Günde en çok üç
deneme — zamanlayıcı dakikada bir koşuyor ve damga sunucusuna
yüklenen bir istemciye dönüşmemeli.

**Doğrulama iki şeyi birden sorar.** Çıpa, (a) o sıradaki kaydın
özetiyle tutuyor mu ve (b) damga gerçekten o özeti mi taşıyor? İlki
zincirin yeniden yazıldığını, ikincisi damganın başka bir veriye ait
olduğunu yakalar. İkisi ayrı sorular, ayrı cevaplanıyor.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import structlog

from talimatname.domain.audit import chain_hash
from talimatname.domain.chain_anchor import ChainAnchor, due, local_day
from talimatname.services.audit import AuditRepository

log = structlog.get_logger(__name__)

DEFAULT_TIMEZONE = "Europe/Istanbul"


@dataclass(frozen=True, slots=True)
class Stamp:
    """Otoriteden dönen damga."""

    token: bytes
    stamped_at: datetime
    tsa_name: str | None = None
    serial: str | None = None


class TimestampError(Exception):
    """Damga alınamadı. Mesajı kayda **kısa** biçimde giriyor."""


class TimestampAuthority(Protocol):
    def stamp(self, digest: bytes) -> Stamp:
        """Özeti tarihletir. Başarısızlıkta `TimestampError` atar."""
        ...

    def covers(self, token: bytes, digest: bytes) -> bool:
        """Damga **bu** özeti mi taşıyor? (imza doğrulaması ayrı)"""
        ...


class AnchorRepository(Protocol):
    def save_anchor(self, anchor: ChainAnchor) -> None: ...

    def anchors(self, *, limit: int = 100) -> list[ChainAnchor]:
        """Çıpalar, **yeniden eskiye**."""
        ...

    def anchors_since(self, moment: datetime) -> list[ChainAnchor]: ...


@dataclass(frozen=True, slots=True)
class AnchorProblem:
    """Çıpa ile zincir arasındaki uyuşmazlık."""

    anchor_id: UUID
    sequence: int
    reason: str


@dataclass(frozen=True, slots=True)
class AnchorReport:
    checked: int
    last_at: datetime | None
    problems: tuple[AnchorProblem, ...]

    @property
    def intact(self) -> bool:
        return not self.problems


class AnchorService:
    def __init__(
        self,
        repo: AnchorRepository,
        audit: AuditRepository,
        authority: TimestampAuthority | None = None,
        *,
        timezone: Callable[[], str] = lambda: DEFAULT_TIMEZONE,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._audit = audit
        self._otorite = authority
        self._saat_dilimi = timezone
        self._now = now

    @property
    def enabled(self) -> bool:
        """Çıpalama yapılandırılmış mı? `/health` ve komut buna bakıyor."""
        return self._otorite is not None

    # --- günlük iş ----------------------------------------------------

    def anchor_due(self) -> ChainAnchor | None:
        """Günün çıpası gerekiyorsa alır. Zamanlayıcı turunun çağırdığı yer.

        Dönen değer yeni çıpa; gerek yoksa None. Saat geçmiş olabilir:
        zamanlayıcı 04:00'te kapalıysa açıldığı anda alınır.
        """
        if self._otorite is None:
            return None

        an = self._now()
        bugun = local_day(an, self._saat_dilimi())
        bugunkuler = self._bugunku_cipalar(bugun)
        if not due(
            an.astimezone(ZoneInfo(self._saat_dilimi())),
            attempts_today=len(bugunkuler),
            has_anchor_today=any(c.state == "ok" for c in bugunkuler),
        ):
            return None
        return self.anchor_now()

    def anchor_now(self) -> ChainAnchor | None:
        """Zincirin **o anki** başını çıpalar; elle de çağrılabilir.

        Günlük iş değil tek seferlik iş: `izi_cipala` komutu bunu
        çağırıyor, zamanlayıcı ise `anchor_due` üzerinden.
        """
        if self._otorite is None:
            return None
        bas = self._audit.head()
        if bas is None:
            log.info("cipa.gunluk_bos")
            return None

        an = self._now()
        temel = ChainAnchor(
            id=uuid4(),
            created_at=an,
            sequence=bas.sequence,
            chain_hash=bas.hash,
        )
        try:
            damga = self._otorite.stamp(temel.digest)
        except Exception as hata:  # otorite her türlü hatayı atabilir
            kayit = ChainAnchor(
                id=temel.id,
                created_at=an,
                sequence=temel.sequence,
                chain_hash=temel.chain_hash,
                state="failed",
                error=_kisa(hata),
            )
            self._repo.save_anchor(kayit.validated())
            log.warning("cipa.alinamadi", sira=temel.sequence, sebep=kayit.error)
            return kayit

        kayit = ChainAnchor(
            id=temel.id,
            created_at=an,
            sequence=temel.sequence,
            chain_hash=temel.chain_hash,
            state="ok",
            token=damga.token,
            stamped_at=damga.stamped_at,
            tsa_name=damga.tsa_name,
            serial=damga.serial,
        )
        self._repo.save_anchor(kayit.validated())
        log.info("cipa.alindi", sira=kayit.sequence, otorite=kayit.tsa_name)
        return kayit

    # --- doğrulama ----------------------------------------------------

    def verify(self, *, limit: int = 100) -> AnchorReport:
        """Çıpaları zincirle karşılaştırır (FR-1302, FR-1304).

        İki soru: kayıt hâlâ aynı mı, damga hâlâ o kaydı mı taşıyor?
        Birincisi tarihin yeniden yazıldığını, ikincisi damganın başka
        bir veriye ait olduğunu yakalar.
        """
        sorunlar: list[AnchorProblem] = []
        cipalar = [c for c in self._repo.anchors(limit=limit) if c.state == "ok"]
        for cipa in cipalar:
            olay = self._audit.at_sequence(cipa.sequence)
            if olay is None:
                sorunlar.append(
                    AnchorProblem(cipa.id, cipa.sequence, "Çıpalanan kayıt günlükte yok")
                )
                continue
            if chain_hash(olay) != cipa.chain_hash:
                sorunlar.append(
                    AnchorProblem(
                        cipa.id,
                        cipa.sequence,
                        "Kaydın özeti çıpayla tutmuyor: o tarihten sonra değişmiş",
                    )
                )
                continue
            damgali = self._otorite is not None and cipa.token is not None
            if damgali and not self._otorite.covers(cipa.token, cipa.digest):  # type: ignore[union-attr,arg-type]
                sorunlar.append(AnchorProblem(cipa.id, cipa.sequence, "Damga bu özeti taşımıyor"))
        return AnchorReport(
            checked=len(cipalar),
            last_at=cipalar[0].stamped_at if cipalar else None,
            problems=tuple(sorunlar),
        )

    def recent(self, *, limit: int = 20) -> list[ChainAnchor]:
        return self._repo.anchors(limit=limit)

    # --- yardımcılar --------------------------------------------------

    def _bugunku_cipalar(self, bugun: date) -> list[ChainAnchor]:
        """Bugünün denemeleri. Sınır **bir gün geriden** alınıyor:

        yerel gün UTC gününden önce başlayabiliyor (Türkiye'de 03:00
        farkı), dar bir pencere bugünün ilk denemesini kaçırırdı.
        """
        dilim = self._saat_dilimi()
        sinir = self._now() - timedelta(days=2)
        return [
            c for c in self._repo.anchors_since(sinir) if local_day(c.created_at, dilim) == bugun
        ]


def _kisa(hata: Exception) -> str:
    """Hatanın kayda giren kısa karşılığı: tür + ilk satır."""
    metin = str(hata).strip().splitlines()[0] if str(hata).strip() else ""
    ad = type(hata).__name__
    return f"{ad}: {metin}"[:200] if metin else ad


__all__ = [
    "AnchorProblem",
    "AnchorReport",
    "AnchorRepository",
    "AnchorService",
    "Stamp",
    "TimestampAuthority",
    "TimestampError",
]
