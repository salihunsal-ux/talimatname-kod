"""Belge doğrulama uç noktası (ST-101; FR-1218) — **oturumsuz**.

```
GET /verify/{code}   → kâğıttaki kodun kaydı
```

Oturum istemiyor: kâğıdı eline alan denetçi ya da müşteri bir kullanıcı
değil, panele giremez. Doğrulanamayan bir belge kodu, kâğıdın üstündeki
güvenceyi süs hâline getirirdi.

Oturumsuz olduğu için üç şeye dikkat edildi:

**Az veri.** Yanıt, kâğıtta zaten yazılı olan alanları doğruluyor
(tür, dönem, şube kodu, üretim zamanı); puanı, madde sonuçlarını,
kimin ürettiğini, IP'yi **vermiyor** (bkz. `services/verification`).

**Hız sınırı.** Kaba ama var (`api/hiz_siniri`): sınırsız bir
oturumsuz uç nokta bedava yük kapısıdır. Sınırın ne olmadığı o modülde
yazılı — gerçek savunma kenar katmanında.

**Kod hesap içinde çözülüyor.** Arama, isteği karşılayan kurulumun
kiracısında yapılıyor (RLS; bkz. `test_db`). Bugün tek hesap var ve
soru çıkmıyor; birden çok hesap tek kuruluma alınırsa kodun hangi
hesapta aranacağı **ayrı bir karar** olacak (hesap başına alan adı
ya da koda taşınan bir hesap öneki). Kiracılar arası arama yapmak,
elinde kod olan herkese başka şirketin kaydını açmak olurdu.

**Sorgu günlüğe yazılmıyor.** Doğrulama isteği olay zincirine
*kaydedilmiyor*: dışarıdan tetiklenen bir yazma, zinciri herkesin
uzatabildiği bir şey yapardı; üstelik kaydetmek, ürünün müşterisi
olmayan insanların IP'sini denetim günlüğüne yazmak olurdu (BR-21).
Teknik günlüğe (structlog) düşüyor, orada kalıyor.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi import Path as YolParametresi
from pydantic import BaseModel, Field

from talimatname.api.bagimliliklar import dogrulama_servisi
from talimatname.api.hiz_siniri import HizSiniri
from talimatname.api.istek import istemci_ip
from talimatname.services.verification import DocumentVerification, VerificationService

log = structlog.get_logger(__name__)

router = APIRouter(tags=["doğrulama"])

Servis = Annotated[VerificationService, Depends(dogrulama_servisi)]

#: Dakikada izin verilen deneme. Elle kod yazan bir insan için fazlasıyla
#: yeterli; sözlük denemesi için anlamsız derecede az.
DENEME_SINIRI = 20
SINIR_PENCERESI = timedelta(minutes=1)

#: Süreç ömrü boyunca yaşıyor (modül düzeyi). Testler `sifirla()` ile
#: temizliyor; istek başına kurulan bir sayaç hiçbir şey saymazdı.
hiz_siniri = HizSiniri(limit=DENEME_SINIRI, period=SINIR_PENCERESI)


class DogrulamaYaniti(BaseModel):
    """Kodun kaydı. Alanlar kâğıtla **karşılaştırma** içindir."""

    code: str = Field(description="Kodun düzenli hâli: XXXX-XXXX-XXXX")
    document: str = Field(description="aylik-ozet | olcum-gunlugu | calistirma")
    document_label: str
    issued_at: datetime = Field(description="Sunucu saati (UTC)")
    timezone: str = Field(description="Kâğıttaki saatin dilimi: hesabın ayarı")
    period: str | None = Field(default=None, description="Raporun dönemi ya da iş günü")
    branch_code: str | None = Field(
        default=None, description="Çalıştırma raporunda şube kodu; dönem raporlarında yok"
    )
    record_intact: bool = Field(description="Kaydın kendi özeti tutuyor: içeriği değişmemiş")
    chain_linked: bool = Field(description="Kayıt zincirde önceki halkaya bağlı")


@router.get(
    "/verify/{code}",
    summary="Belge kodunu doğrula (FR-1218)",
    description=(
        "Kâğıt üstündeki belge kodunun olay günlüğündeki kaydını döner. "
        "Oturum gerekmez. Kaydın kendi özeti ve önceki halkaya bağı sınanır; "
        "zincirin tamamının doğrulanması işletmecinin aracındadır."
    ),
)
def belge_dogrula(
    code: Annotated[str, YolParametresi(max_length=40, description="XXXX-XXXX-XXXX")],
    request: Request,
    servis: Servis,
) -> DogrulamaYaniti:
    hiz_siniri.zorunlu_kil(istemci_ip(request))
    sonuc = servis.check(code)
    log.info(
        "belge.dogrulandi",
        tur=sonuc.document,
        saglam=sonuc.trustworthy,
    )
    return _yanit(sonuc)


def _yanit(sonuc: DocumentVerification) -> DogrulamaYaniti:
    return DogrulamaYaniti(
        code=sonuc.code,
        document=sonuc.document,
        document_label=sonuc.document_label,
        issued_at=sonuc.issued_at,
        timezone=sonuc.timezone,
        period=sonuc.period,
        branch_code=sonuc.branch_code,
        record_intact=sonuc.record_intact,
        chain_linked=sonuc.chain_linked,
    )
