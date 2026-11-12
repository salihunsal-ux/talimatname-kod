"""Spike A ölçek koşumu: 500 kanıt, iki cihaz, 100 tekrar.

`test_spike_a_senk.py` ile aynı taklitçiyi kullanır ama büyük koşar;
bu yüzden süitin içinde değil, elle çalıştırılır (dosya adı `test_` ile
başlamadığı için pytest toplamaz):

    python tests/spike_a_olcek.py

ADR-0013'ün Spike A kabulü: *72 saat çevrimdışı, 500 kanıt, iki cihaz
aynı çalıştırma; 100 tekrarda sıfır kayıp, sıfır çift kayıt.* Flutter
yok, yani ölçülen şey sunucu sözleşmesi: kuyruğun tamamı kayıpsız
yazılıyor mu, tekrar gönderim çiftleme yapıyor mu, iki cihaz aynı
çalıştırmada çakışıyor mu.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# **Bellek modu, içe almadan önce.** Süitte bunu `conftest`in
# `bellek_modu` fixture'ı yapıyor; betik fixture çalıştırmıyor, yani
# bu satır olmadan `.env`deki geliştirme veritabanına bağlanıp oraya
# deneme planı yazıyor. İlk koşumda tam bu oldu.
os.environ["DATABASE_URL"] = ""

sys.path.insert(0, str(Path(__file__).parent))

from fastapi.testclient import TestClient

from conftest import oturum_ac
from talimatname.api.app import create_app
from talimatname.settings import Settings, get_settings
from test_spike_a_senk import Cihaz, _maddeler, _yazilabilir

HEDEF_KANIT = 500
TEKRAR = 100


def _plan_kur(istemci: TestClient, sube_id: str, sira: int) -> None:
    """Plan açmak yönetici işi; belirteç geçici olarak çevrilir."""
    from test_execution import _yazilabilir_plan_kur

    cagiranin = istemci.headers.get("Authorization")
    oturum_ac(istemci, "admin")
    try:
        _yazilabilir_plan_kur(istemci, sube_id, sira)
    finally:
        if cagiranin is not None:
            istemci.headers["Authorization"] = cagiranin


def _calistirmalar(istemci: TestClient) -> list[tuple[str, list[dict[str, Any]]]]:
    """Hedef kanıt sayısına yetecek kadar yazılabilir çalıştırma kurar.

    Her plan aynı şubede ayrı bir çalıştırma doğuruyor; madde başına en
    çok 3 kanıt olduğu için gereken plan sayısı madde sayısından çıkıyor.
    """
    subeler = [s for d in istemci.get("/api/v1/branches").json() for s in d["branches"]]
    for sube in subeler:  # kapalı günü olan şube çalıştırma üretmez (BR-17)
        _plan_kur(istemci, sube["id"], 900)
        if _yazilabilir(istemci.get("/api/v1/sync/manifest").json()):
            break
    else:
        return []

    acik = _yazilabilir(istemci.get("/api/v1/sync/manifest").json())
    madde_sayisi = len(_maddeler(istemci, acik[0]["template_version_id"]))
    gereken = -(-HEDEF_KANIT // (madde_sayisi * 3))
    print(f"  madde/çalıştırma: {madde_sayisi} · gereken çalıştırma: {gereken}")
    for sira in range(1, gereken):
        _plan_kur(istemci, acik[0]["branch_id"], 900 + sira)

    acik = _yazilabilir(istemci.get("/api/v1/sync/manifest").json())
    sonuc = [(r["run_id"], _maddeler(istemci, r["template_version_id"])) for r in acik]
    yuva = sum(len(m) for _, m in sonuc) * 3
    print(f"  yazılabilir çalıştırma: {len(sonuc)} · kanıt yuvası {yuva}")
    return sonuc


def _doldur(cihaz: Cihaz, calistirmalar: list[tuple[str, list[dict[str, Any]]]]) -> int:
    """Çevrimdışı kuyruğu HEDEF_KANIT kanıta kadar doldurur."""
    kanit = 0
    for run_id, maddeler in calistirmalar:
        for madde in maddeler:
            kalan = min(3, HEDEF_KANIT - kanit)
            if kalan <= 0:
                return kanit
            aid = cihaz.cevapla(run_id, madde, kanit_sayisi=kalan)
            for kare in range(kalan):
                cihaz.fotografla(run_id, aid, madde, f"{run_id[:8]}-{madde['id'][:8]}-{kare}")
                kanit += 1
    return kanit


def main() -> int:
    # Kanıtlar geçici dizine: 500 PNG depoya düşmemeli.
    kanit_dizini = tempfile.mkdtemp(prefix="spike_a_kanit_")
    istemci = oturum_ac(
        TestClient(create_app(Settings(evidence_dir=kanit_dizini))), "branch_manager"
    )

    assert not get_settings().database_url, "betik veritabanına bağlı: bellek modu kurulmamış"

    print("Spike A · ölçek koşumu")
    calistirmalar = _calistirmalar(istemci)
    if not calistirmalar:
        print("  yazılabilir çalıştırma kurulamadı")
        return 1

    cihaz = Cihaz(istemci, "A")
    _doldur(cihaz, calistirmalar)
    print(f"  kuyruk: {len(cihaz.kuyruk.cevaplar)} cevap · {len(cihaz.kuyruk.kanitlar)} kanıt")

    # 72 saat çevrimdışı kalmış bir cihazın ilk senki.
    basla = time.monotonic()
    ilk = cihaz.senkle(device_time=datetime.now(UTC) - timedelta(hours=72))
    sure = time.monotonic() - basla
    print(
        f"  ilk senk: {sure:.1f} sn · kabul {ilk.kabul_cevap} cevap / {ilk.kabul_kanit} kanıt · "
        f"yüklenen {ilk.yuklenen} · red {ilk.red_cevap}+{ilk.red_kanit} · tekrar {ilk.tekrar_kanit}"
    )
    if ilk.hatalar:
        print("  ret sebepleri:", dict(Counter(ilk.hatalar)))

    # Tekrar gönderim: aynı kuyruk, iki cihaz dönüşümlü, TEKRAR kez.
    run_id, maddeler = calistirmalar[0]
    ikinci = Cihaz(istemci, "B")
    for madde in maddeler[:3]:
        ikinci.cevapla(run_id, madde, "failed")

    basla = time.monotonic()
    tekrar_hata: list[str] = []
    for tur in range(TEKRAR):
        sonuc = (cihaz if tur % 2 == 0 else ikinci).senkle()
        tekrar_hata.extend(sonuc.hatalar)
    sure = time.monotonic() - basla
    print(f"  {TEKRAR} tekrar (A/B dönüşümlü): {sure:.1f} sn")
    if tekrar_hata:
        print("  tekrarlarda ret:", dict(Counter(tekrar_hata)))

    # Doğrulama: her maddede tek cevap satırı, her kanıt tek kayıt.
    cift = 0
    toplam_cevap = 0
    depolanan = 0
    for rid, _ in calistirmalar:
        gorunum = istemci.get(f"/api/v1/runs/{rid}").json()
        kimlikler = [
            m["item_id"] for b in gorunum["sections"] for m in b["items"] if m.get("answer")
        ]
        toplam_cevap += len(kimlikler)
        cift += len(kimlikler) - len(set(kimlikler))
        kayitlar = istemci.get(f"/api/v1/runs/{rid}/evidence").json()
        depolanan += len([k for k in kayitlar if k.get("status") == "stored"])

    print(f"  sunucuda: {toplam_cevap} cevap satırı · {depolanan} depolanmış kanıt · çift {cift}")

    gecti = (
        cift == 0
        and ilk.red_cevap == 0
        and ilk.red_kanit == 0
        and ilk.kabul_cevap == len(cihaz.kuyruk.cevaplar)
        and ilk.yuklenen == len(cihaz.kuyruk.kanitlar)
        and depolanan == len(cihaz.kuyruk.kanitlar)
        and not tekrar_hata
    )
    print()
    print("SONUÇ:", "geçti" if gecti else "GEÇMEDİ")
    return 0 if gecti else 1


if __name__ == "__main__":
    sys.exit(main())
