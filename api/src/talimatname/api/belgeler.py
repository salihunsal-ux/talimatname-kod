"""Kâğıda basılan belgelerin ortak başı: marka ve belge kodu (FR-1218).

İki uç nokta kümesi (raporlar, çalıştırma) aynı iki şeyi yapıyor:
kâğıdın üstüne hangi hesabın adını yazacağını bulmak ve raporu olay
günlüğüne kaydedip oradan dönen kodu kâğıda koymak. İkisi de iki
dosyada ayrı ayrı duruyordu; kodun biçimi değiştiğinde ya da günlüğe
yazılan alanlar arttığında birini güncelleyip ötekini atlamak çok
kolaydı — doğrulama sayfası ise **tek** biçim bekliyor.
"""

from __future__ import annotations

from uuid import UUID

from talimatname.api.bagimliliklar import ayarlar
from talimatname.domain.audit import format_code
from talimatname.services.audit import AuditService
from talimatname.services.pdf import Brand
from talimatname.services.setup import SetupService


def marka(kurulum: SetupService) -> Brand:
    """Kâğıdın üstündeki hesap adı, saat dilimi ve doğrulama adresi.

    Sihirbaz bitmemişse marka adı henüz yok: rapor üretilir ama
    kâğıtta ürünün adı görünür. Üretmemek daha kötü olurdu — kurulumun
    ortasında da rapor alınabilmeli.
    """
    adres = ayarlar().verify_url
    ayar = kurulum.settings()
    if ayar is None:
        return Brand(name="Talimatname", verify_url=adres)
    return Brand(name=ayar.brand_name, timezone=ayar.timezone, verify_url=adres)


def belge_kodu(
    iz: AuditService,
    *,
    tur: str,
    icerik_kodu: str,
    donem: str | None = None,
    sube: str | None = None,
    nesne_turu: str = "rapor",
    nesne_id: UUID | None = None,
) -> str | None:
    """Raporu olay günlüğüne yazar ve kâğıttaki kodu döner (FR-1218).

    Kâğıttaki kod, **olayın zincir özeti**: doğrulama sayfası koda göre
    bu kaydı buluyor. Kaydın içinde raporun içerik kodu da duruyor,
    böylece "hangi veri dökülmüş" sorusu da cevaplanıyor.

    `donem` ve `sube` kayda yazılıyor çünkü doğrulama sayfası bunları
    gösteriyor: denetçi elindeki kâğıtla karşılaştırabilsin. Fazlası
    (puan, madde sonuçları, kimin ürettiği) **yazılmıyor** — sayfa onu
    göstermiyor, günlüğe de iş için gerekmeyen veri girmemeli (BR-21).

    Günlük yazılamazsa None dönüyor: rapor yine üretiliyor ama kâğıtta
    kodun zincire bağlı **olmadığı** yazıyor. Bağlıymış gibi yazmak,
    olmayan bir güvence vermek olurdu.
    """
    ozet: dict[str, object] = {"tur": tur, "icerik": icerik_kodu}
    if donem is not None:
        ozet["donem"] = donem
    if sube is not None:
        ozet["sube"] = sube
    olay = iz.record(
        "rapor.uretildi",
        object_type=nesne_turu,
        object_id=nesne_id,
        after=ozet,
    )
    return format_code(olay.hash) if olay else None


__all__ = ["belge_kodu", "marka"]
