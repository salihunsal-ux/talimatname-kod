"""Olay günlüğü servisi (ST-099, ST-100; FR-1301, FR-1304).

Günlüğün tek yazma yolu burası. Üç şey burada çözülüyor:

**Zincirin başı.** Yeni olay, son olayın özetini taşır. İki istek aynı
anda yazarsa ikisi de aynı başı okuyup zinciri **çatallayabilir**; bu
yüzden (hesap, sıra) tekil ve çakışmada kısa bir yeniden deneme var.
Kilitle sıraya dizmek yerine çakışmayı yakalamak seçildi: çakışma
nadir, kilit her yazmada maliyet.

**İstek bağlamı.** IP ve cihaz, servisin kendi bildiği şeyler değil;
`RequestContext` ile dışarıdan geliyor (ADR-0014: alan katmanı
saat ve I/O bilmez, servis de HTTP bilmez).

**Yazma hiçbir işi düşürmez.** Günlük yazılamadığı için bir kanıt
yüklemesi ya da oturum açma başarısız olmamalı: hata günlüğe yazılır
ve iş sürer. Denetim izi değerli ama ürünün kendisi değil; tersi
seçim, günlük tablosundaki bir aksaklığı bütün ürünün durması hâline
getirirdi. Kırılma `verify` ile zaten görülür.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import structlog

from talimatname.domain.audit import (
    GENESIS,
    AuditEvent,
    ChainBreak,
    SequenceTaken,
    sealed,
    summary_of,
    verify_chain,
)

log = structlog.get_logger(__name__)

#: Sıra çakışmasında kaç kez yeniden denenir. Çakışma iki isteğin
#: aynı anda yazmasıyla oluşuyor; üçüncü denemede hâlâ çakışıyorsa
#: sorun yoğunluk değil başka bir şeydir ve görünmeli.
MAX_RETRY = 3


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Olayın "nereden" kısmı (FR-1301).

    IP ve cihaz isteğe bağlı: zamanlayıcı turunda ikisi de yok ve
    uydurmak, günlüğü okuyana yanlış bilgi vermek olurdu.
    """

    actor_id: UUID | None = None
    ip: str | None = None
    device: str | None = None


#: İsteğin bağlamı. Neden contextvar: "kim, nereden" bilgisi HTTP
#: katmanında biliniyor ama olayı yazan yer servisin derinliği
#: (kanıt, yürütme). Bu bilgiyi her servis imzasına parametre olarak
#: eklemek, HTTP'yi bütün katmanlara sızdırırdı (ADR-0014).
#: İsteğin bağlamı **kutu içinde** tutuluyor. Nedeni ince ama önemli:
#: FastAPI eşzamanlı (sync) bağımlılıkları ve uç noktaları ayrı
#: iş parçacıklarında koşturuyor ve her biri contextvar'ın bir
#: **kopyasını** alıyor. Kopyaya yazmak çağıranı etkilemez; bu yüzden
#: belirteç çözülünce eklenen aktör uç noktaya ulaşmıyordu. Kutu
#: referansla paylaşıldığı için içine yazılan her yerden görünüyor.
#:
#: Varsayılan None: bağlamsız çağrı (zamanlayıcı turu, betik) ile
#: "boş bağlam" aynı şey ve ikisinde de IP uydurulmuyor.
@dataclass
class _Kutu:
    context: RequestContext


_ISTEK_BAGLAMI: ContextVar[_Kutu | None] = ContextVar("izi_baglami", default=None)


def current_context() -> RequestContext:
    kutu = _ISTEK_BAGLAMI.get()
    return kutu.context if kutu else RequestContext()


def set_actor(actor_id: UUID) -> None:
    """Bağlama aktörü ekler: belirteç çözülünce kim olduğu belli olur.

    Ara katman isteği karşılarken IP ve cihazı biliyor ama kullanıcıyı
    bilmiyor (belirteç henüz çözülmedi). Bu yüzden aktör sonradan,
    `guvenlik.gecerli_kullanici` içinden yazılıyor.
    """
    kutu = _ISTEK_BAGLAMI.get()
    if kutu is not None:
        kutu.context = replace(kutu.context, actor_id=actor_id)


@contextmanager
def using_context(context: RequestContext) -> Iterator[None]:
    """İstek boyunca bağlamı kurar; çıkışta **eski değerine döner**.

    Sıfırlamak değil geri almak: zamanlayıcı turu bir isteğin içinden
    tetiklenebiliyor ve dönüşte isteğin bağlamı kaybolmamalı.
    """
    jeton = _ISTEK_BAGLAMI.set(_Kutu(context))
    try:
        yield
    finally:
        _ISTEK_BAGLAMI.reset(jeton)


class AuditRepository:
    """Kalıcılık portu. **Güncelleme ve silme yok** (FR-1301, TC-100).

    Port yüzeyinde böyle bir yöntem bulunmaması bilinçli: ekle-yalnızlık
    yalnızca veritabanı yetkisiyle değil, kodun şekliyle de korunuyor.
    """

    def append(self, event: AuditEvent) -> None:  # pragma: no cover - arayüz
        """Olayı yazar. Sıra alınmışsa `SequenceTaken` fırlatır."""
        raise NotImplementedError

    def head(self) -> AuditEvent | None:  # pragma: no cover - arayüz
        """Zincirin son halkası; hiç olay yoksa None."""
        raise NotImplementedError

    def events(  # pragma: no cover - arayüz
        self,
        *,
        object_id: UUID | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 200,
    ) -> list[AuditEvent]:
        """Sıraya göre artan olaylar."""
        raise NotImplementedError


class AuditService:
    def __init__(
        self,
        repo: AuditRepository,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._now = now

    def record(
        self,
        event_type: str,
        *,
        object_type: str,
        object_id: UUID | None = None,
        context: RequestContext | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> AuditEvent | None:
        """Olayı zincire ekler. Yazamazsa **None** döner, iş durmaz.

        Dönen değer çağrı yerinde genelde kullanılmıyor; rapor
        doğrulama kodu (FR-1218) için olayın özeti gerekiyor.
        """
        once, sonra = summary_of(before, after)
        baglam = context or current_context()

        for deneme in range(MAX_RETRY):
            bas = self._repo.head()
            olay = sealed(
                AuditEvent(
                    id=uuid4(),
                    sequence=(bas.sequence + 1) if bas else 1,
                    event_type=event_type,
                    at=self._now(),
                    object_type=object_type,
                    object_id=object_id,
                    actor_id=baglam.actor_id,
                    ip=baglam.ip,
                    device=baglam.device,
                    before=once,
                    after=sonra,
                    prev_hash=bas.hash if bas else GENESIS,
                )
            )
            try:
                self._repo.append(olay)
            except SequenceTaken:
                log.info("izi.sira_cakismasi", deneme=deneme + 1, tur=event_type)
                continue
            except Exception:
                log.exception("izi.yazilamadi", tur=event_type)
                return None
            return olay

        log.warning("izi.sira_cakismasi_asildi", tur=event_type)
        return None

    # --- okuma ve doğrulama (FR-1304) --------------------------------

    def for_object(self, object_id: UUID, *, limit: int = 200) -> list[AuditEvent]:
        """Bir çalıştırmanın/aksiyonun izi: denetim izi ekranının verisi."""
        return self._repo.events(object_id=object_id, limit=limit)

    def verify(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50_000,
    ) -> ChainVerification:
        """Zinciri yeniden hesaplar (ST-100, TC-101).

        Aralık verilirse, aralıktan **önceki** kaydın özeti beklenen
        başlangıç olur: son ayı doğrulamak için bütün günlüğü okumak
        gerekmesin.
        """
        olaylar = self._repo.events(since=since, until=until, limit=limit)
        baslangic = GENESIS
        if olaylar and olaylar[0].sequence > 1:
            # Aralığın hemen öncesi: beklenen başlangıç onun özeti.
            onceki = self._repo.events(until=olaylar[0].at, limit=limit)
            oncekiler = [o for o in onceki if o.sequence < olaylar[0].sequence]
            if oncekiler:
                baslangic = oncekiler[-1].hash
        kirilmalar = verify_chain(olaylar, expected_start=baslangic)
        return ChainVerification(
            checked=len(olaylar),
            first_sequence=olaylar[0].sequence if olaylar else None,
            last_sequence=olaylar[-1].sequence if olaylar else None,
            breaks=tuple(kirilmalar),
        )


@dataclass(frozen=True, slots=True)
class ChainVerification:
    """Doğrulama raporu (FR-1304)."""

    checked: int
    first_sequence: int | None
    last_sequence: int | None
    breaks: tuple[ChainBreak, ...]

    @property
    def intact(self) -> bool:
        return not self.breaks


def tampered(event: AuditEvent, **degisiklik: Any) -> AuditEvent:
    """Testlerin ve iç aracın "kaydı elle değiştir" yardımcısı (TC-101).

    Özet **yeniden hesaplanmaz**: değişikliğin zinciri kırdığını
    görmek için var.
    """
    return replace(event, **degisiklik)
