"""Demoyu geçmiş tamamlanmış çalıştırmalarla doldurur.

Neden: aylık rapor %3 zamanında tamamlanma gösteriyordu (106 çalıştırma,
1 zamanında, 38 kaçırıldı). Sayılar doğruydu, çünkü demoda kimse liste
doldurmamıştı — ama bir zincire gösterilecek hikâye olarak işe yaramaz
(bağımsız test turu DK-1).

Nasıl: **gerçek servisler** kullanılıyor. Cevaplar `ExecutionService`
üzerinden yazılıyor, gönderim `submit` ile yapılıyor; puan, sonuç,
kritik aksiyon ve denetim izi normal yoldan oluşuyor. Servisin saati
çalıştırmanın penceresine ayarlanıyor — pencere kuralını (BR-02/BR-03)
delmek için değil, geçmişte o saatte yapılmış gibi yazmak için.

Dürüstlük: fotoğraf zorunlu maddelere **belirgin bir yer tutucu görsel**
yükleniyor. Kanıt sayısını elle uydurmak ("fotoğraf var" demek) bu
ürünün tam da iddia ettiği şeyi yalanlardı; onun yerine gerçekten bir
dosya var ve ne olduğu belli.

Kullanım (sunucuda, api konteyneri içinde):

    python -m talimatname.araclar.demo_doldur --gun 28
    python -m talimatname.araclar.demo_doldur --gun 28 --kuru   # yazmadan özet
"""

from __future__ import annotations

import argparse
import hashlib
import random
import struct
import sys
import zlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

from talimatname.api import bagimliliklar
from talimatname.domain.plans import Run
from talimatname.services.evidence import EvidenceService
from talimatname.services.execution import ExecutionService

#: Çalıştırma kimliğinden türeyen sabit tohum: betik iki kez koşarsa
#: aynı çalıştırma aynı sonucu alır, demo her seferinde değişmez.
TOHUM_UZAYI = UUID("7c1f5c1e-0000-4000-8000-000000000001")

#: Gerçekçi bir zincirin dağılımı. Kusursuz %100 inandırıcı değil;
#: kaçırılmış ve başarısız kalmadan "izlemeye değer" hissi oluşmuyor.
ZAMANINDA = 0.78
GEC = 0.09
BASARISIZ = 0.05
# kalanı (≈ %8) kaçırılmış bırakılıyor: hiç dokunulmuyor.


def yer_tutucu_png(etiket: str) -> bytes:
    """Tek renkli küçük PNG. Gerçek fotoğraf değil ve öyle görünmüyor."""
    en = boy = 64
    tohum = int(hashlib.sha256(etiket.encode()).hexdigest()[:6], 16)
    r, g, b = (tohum >> 16) & 0x7F, (tohum >> 8) & 0x7F, tohum & 0x7F
    satirlar = b"".join(b"\x00" + bytes([r, g, b]) * en for _ in range(boy))

    def parca(tur: bytes, veri: bytes) -> bytes:
        return (
            struct.pack(">I", len(veri))
            + tur
            + veri
            + struct.pack(">I", zlib.crc32(tur + veri) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + parca(b"IHDR", struct.pack(">IIBBBBB", en, boy, 8, 2, 0, 0, 0))
        + parca(b"IDAT", zlib.compress(satirlar, 9))
        + parca(b"IEND", b"")
    )


def saat_kurulu_servisler(an: datetime) -> tuple[ExecutionService, EvidenceService]:
    """Saati verilen ana sabitlenmiş yürütme ve kanıt servisi."""
    kanit = EvidenceService(
        bagimliliklar._kanit_deposu(),
        bagimliliklar._plan_deposu(),
        bagimliliklar._org_deposu(),
        bagimliliklar._nesne_deposu(),
        bagimliliklar._kullanici_deposu(),
        settings=bagimliliklar.ayarlar(),
        audit=bagimliliklar.izi_servisi(),
        now=lambda: an,
    )
    yurutme = ExecutionService(
        bagimliliklar._cevap_deposu(),
        bagimliliklar._plan_deposu(),
        bagimliliklar._sablon_deposu(),
        bagimliliklar._aksiyon_deposu(),
        verified_evidence=kanit.verified_counts,
        audit=bagimliliklar.izi_servisi(),
        now=lambda: an,
        prep_minutes=bagimliliklar.ayarlar().run_prep_minutes,
    )
    return yurutme, kanit


def kanit_yukle(
    kanit: EvidenceService, *, run_id: UUID, answer_id: UUID, item_id: UUID, kisi: UUID | None
) -> None:
    baytlar = yer_tutucu_png(f"{run_id}:{item_id}")
    kayit, belirtec = kanit.start(
        run_id=run_id,
        answer_id=answer_id,
        item_id=item_id,
        sha256=hashlib.sha256(baytlar).hexdigest(),
        content_type="image/png",
        size_bytes=len(baytlar),
        user_id=kisi,
        from_gallery=True,  # galeriden: demo görseli, o an çekilmedi
    )
    kanit.receive(belirtec, baytlar)
    kanit.complete(kayit.id)


def calistirmayi_doldur(run: Run, *, basarisiz_mi: bool, gec_mi: bool, kisi: UUID | None) -> str:
    """Tek çalıştırmayı cevaplayıp gönderir; sonucu anlatan satır döner."""
    # Gönderim anı: pencere içinde ya da (geç ise) pencereden sonra,
    # tolerans bitmeden. Yazma anı her hâlükârda pencere içinde.
    yazma_ani = run.window_start + timedelta(minutes=10)
    gonderim_ani = (
        run.window_end + timedelta(minutes=10) if gec_mi else run.window_end - timedelta(minutes=5)
    )

    yurutme, kanit = saat_kurulu_servisler(yazma_ani)
    surum = yurutme._version(run)
    maddeler = [m for m in surum.items if m.scored]
    if not maddeler:
        return f"{run.id} atlandı: puanlanır madde yok"

    rastgele = random.Random(str(uuid5(TOHUM_UZAYI, str(run.id))))
    # Başarısız çalıştırmada tek bir madde düşürülüyor: hepsi kırmızı
    # olan bir liste gerçekçi değil.
    dusen = rastgele.choice(maddeler) if basarisiz_mi else None

    for madde in maddeler:
        answer_id = uuid5(TOHUM_UZAYI, f"cevap:{run.id}:{madde.id}")
        duser = madde is dusen
        durum = "failed" if duser else "passed"
        deger = None
        if getattr(madde, "type", None) == "temperature":
            # Kabul aralığının içinden bir değer; düşerse dışından.
            alt = madde.min_value if madde.min_value is not None else 0
            ust = madde.max_value if madde.max_value is not None else 8
            deger = str(round(rastgele.uniform(float(alt), float(ust)), 1))
            if duser:
                deger = str(round(float(ust) + 3, 1))
        elif getattr(madde, "type", None) == "text":
            deger = "Devir sorunsuz."

        yurutme.write_answer(
            run_id=run.id,
            answer_id=answer_id,
            item_id=madde.id,
            state=durum,
            value=deger,
            note="Demo: madde kabul ölçütünü karşılamadı." if duser else None,
            user_id=kisi,
        )
        # Fotoğraf zorunlu maddeye ve düşen maddeye kanıt gerekiyor
        # (BR-06): ikisinde de yer tutucu görsel yükleniyor.
        if madde.photo_required or duser:
            kanit_yukle(kanit, run_id=run.id, answer_id=answer_id, item_id=madde.id, kisi=kisi)

    yurutme_g, _ = saat_kurulu_servisler(gonderim_ani)
    sonuc = yurutme_g.submit(run.id, user_id=kisi)
    etiket = "geç" if gec_mi else "zamanında"
    return f"{run.id} {etiket} · {sonuc.result} · %{sonuc.score_percent}"


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--gun", type=int, default=28, help="Kaç gün geriye doldurulsun")
    ayristirici.add_argument("--kuru", action="store_true", help="Yazma, yalnızca özet göster")
    secenekler = ayristirici.parse_args()

    bagimliliklar._ilk_tur()
    planlar = bagimliliklar._plan_deposu()
    an = datetime.now(UTC)
    en_eski = an - timedelta(days=secenekler.gun)

    adaylar = [
        r
        for r in planlar.runs()
        # Yalnızca **geçmiş** çalıştırmalar: bugünün ve geleceğin
        # listelerine dokunulmuyor, demoyu gezen kişi onları kendi
        # dolduracak.
        if r.tolerance_end < an
        and r.window_start >= en_eski
        and r.status in ("scheduled", "in_progress")
    ]
    adaylar.sort(key=lambda r: r.window_start)
    print(f"aday çalıştırma: {len(adaylar)} ({secenekler.gun} gün)")

    sayac = {"zamanında": 0, "geç": 0, "başarısız": 0, "kaçırıldı": 0, "hata": 0}
    for run in adaylar:
        zar = random.Random(str(uuid5(TOHUM_UZAYI, f"zar:{run.id}"))).random()
        if zar < ZAMANINDA:
            tur, gec, basarisiz = "zamanında", False, False
        elif zar < ZAMANINDA + GEC:
            tur, gec, basarisiz = "geç", True, False
        elif zar < ZAMANINDA + GEC + BASARISIZ:
            tur, gec, basarisiz = "başarısız", False, True
        else:
            sayac["kaçırıldı"] += 1
            continue

        if secenekler.kuru:
            sayac[tur] += 1
            continue
        try:
            print(" ", calistirmayi_doldur(run, basarisiz_mi=basarisiz, gec_mi=gec, kisi=None))
            sayac[tur] += 1
        except Exception as hata:
            print(f"  {run.id} HATA: {type(hata).__name__}: {hata}")
            sayac["hata"] += 1

    print("özet:", ", ".join(f"{k}={v}" for k, v in sayac.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
