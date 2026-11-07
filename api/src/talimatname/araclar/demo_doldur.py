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
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid5

from talimatname.api import bagimliliklar
from talimatname.domain.plans import Run, plan_runs
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
    *, run_id: UUID, answer_id: UUID, item_id: UUID, kisi: UUID | None, cekim: datetime
) -> None:
    """Yer tutucu görseli kanıt olarak yükler.

    Yükleme belirteci **gerçek saatle** imzalanıyor: geçmiş saatle
    imzalanan belirtecin süresi daha doğarken dolmuş oluyor. Dosya
    bugün yükleniyor, `captured_at` ise listenin doldurulduğu ana
    yazılıyor — demoda olan tam olarak bu ve kayıt da bunu söylüyor.
    """
    _, kanit = saat_kurulu_servisler(datetime.now(UTC))
    baytlar = yer_tutucu_png(f"{run_id}:{item_id}")

    # Betik yarıda kalmış olabilir: kayıt açılmış ama baytlar gitmemiş
    # ya da doğrulanmamış olabilir. Yeniden `start` çağırmak
    # `DuplicateEvidence` verir; kaldığı yerden sürdürülüyor.
    for var in kanit.for_run(run_id):
        if var.item_id != item_id:
            continue
        kayit_var, belirtec_var = kanit.resume(var.id)
        if belirtec_var is None:
            if kayit_var.status == "pending":
                kanit.complete(kayit_var.id)
            return
        kanit.receive(belirtec_var, baytlar)
        kanit.complete(kayit_var.id)
        return

    kayit, belirtec = kanit.start(
        run_id=run_id,
        answer_id=answer_id,
        item_id=item_id,
        sha256=hashlib.sha256(baytlar).hexdigest(),
        content_type="image/png",
        size_bytes=len(baytlar),
        user_id=kisi,
        from_gallery=True,  # galeriden: demo görseli, o an çekilmedi
        captured_at=cekim,
    )
    kanit.receive(belirtec, baytlar)
    kanit.complete(kayit.id)


def calistirmayi_doldur(run: Run, *, basarisiz_mi: bool, gec_mi: bool, kisi: UUID | None) -> str:
    """Tek çalıştırmayı cevaplayıp gönderir; sonucu anlatan satır döner."""
    # Zamanlar pencereye sığacak biçimde sıkıştırılıyor: kısa pencereli
    # ya da toleransı sıfır planlarda sabit +10 dk tolerans bitişini
    # aşıyor ve sunucu haklı olarak `pencere-kapali` diyordu.
    son_an = run.tolerance_end - timedelta(minutes=1)
    yazma_ani = min(run.window_start + timedelta(minutes=10), son_an)
    if gec_mi and run.tolerance_end <= run.window_end:
        gec_mi = False  # tolerans yok: "geç" diye bir hâl de yok
    gonderim_ani = (
        min(run.window_end + timedelta(minutes=10), son_an)
        if gec_mi
        else max(run.window_end - timedelta(minutes=5), yazma_ani)
    )
    gonderim_ani = min(gonderim_ani, son_an)

    yurutme, _ = saat_kurulu_servisler(yazma_ani)
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
            kanit_yukle(
                run_id=run.id,
                answer_id=answer_id,
                item_id=madde.id,
                kisi=kisi,
                cekim=yazma_ani,
            )

    yurutme_g, _ = saat_kurulu_servisler(gonderim_ani)
    sonuc = yurutme_g.submit(run.id, user_id=kisi)
    etiket = "geç" if gec_mi else "zamanında"
    return f"{run.id} {etiket} · {sonuc.result} · %{sonuc.score_percent}"


def gecmis_calistirmalar(ilk: date, bitis: date, an: datetime, *, kuru: bool) -> list[Run]:
    """[ilk, bitis) aralığına çalıştırma üretir ve doldurulacakları döndürür.

    Zamanlayıcı yalnızca **ileriye** üretiyor (FR-0513), o yüzden demoda
    geçmiş yok. Burada aynı pencere motoruyla geriye üretiliyor.

    `bitis` demonun kendi geçmişini korur: o günden **sonraki** hiçbir
    çalıştırmaya dokunulmuyor. Demoyu gezerken kaçırılan liste
    kaçırılmış kalır — sonradan doldurmak geçmişi düzeltmek olurdu
    (BR-03). Sınırın gerisi ise tohum verisi: hiç yaşanmamış bir geçmiş
    kuruluyor, var olan bir kayıt düzeltilmiyor. Bu yüzden orada
    "kaçırıldı" damgası taşıyan (zamanlayıcının bu betiğin yarım kalan
    turundan sonra damgaladığı) kayıtlar da doldurulabiliyor.
    """
    planlar = bagimliliklar._plan_deposu()
    org = bagimliliklar._org_deposu()
    mevcut = {r.id: r for r in planlar.runs()}

    yeni: list[Run] = []
    for plan in planlar.plans():
        if not plan.active:
            continue
        for branch_id in plan.branch_ids:
            sube = org.branch(branch_id)
            if sube is None or sube.status != "active":
                continue
            for kosu in plan_runs(plan, branch_id, sube.calendar(), ilk, bitis - timedelta(days=1)):
                if kosu.tolerance_end >= an:
                    continue
                var = mevcut.get(kosu.id)
                if var is not None:
                    # Gönderilmiş ya da iptal edilmişe dokunulmaz.
                    if var.status not in ("submitted", "cancelled"):
                        yeni.append(var)
                    continue
                if not kuru:
                    planlar.save_run(kosu)
                yeni.append(kosu)

    yeni.sort(key=lambda r: r.window_start)
    return yeni


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--gun", type=int, default=28, help="Kaç gün geriye doldurulsun")
    ayristirici.add_argument(
        "--bitis",
        required=True,
        help="Bu günden (YYYY-AA-GG) sonrasına dokunulmaz: demonun kendi geçmişi korunur",
    )
    ayristirici.add_argument("--kuru", action="store_true", help="Yazma, yalnızca özet göster")
    secenekler = ayristirici.parse_args()

    bagimliliklar._ilk_tur()
    an = datetime.now(UTC)
    en_eski = an - timedelta(days=secenekler.gun)

    bitis = date.fromisoformat(secenekler.bitis)
    adaylar = gecmis_calistirmalar(en_eski.date(), bitis, an, kuru=secenekler.kuru)
    print(f"aday çalıştırma: {len(adaylar)} ({en_eski.date()} → {bitis}, hariç)")

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
