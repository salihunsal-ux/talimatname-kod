"""Kaçırma aksiyonlarını gruplamaya geçirir (tek seferlik).

Kaçırma aksiyonunun kimliği **çalıştırmadan** türüyordu; artık (şube,
plan, iş günü) üçlüsünden türüyor. Yükseltmeden sonra eski satırlar
yerinde kalıyor ve yenileri yanlarına açılıyor: aynı kaçırma iki kez
görünüyor.

Bu betik eski satırları **kapatır**, silmez. Silmek bir iş kaydını yok
etmek olurdu; kapatma notu neden kapatıldığını söylüyor ve olay
günlüğünde duruyor.

    python -m talimatname.araclar.kacirma_aksiyonlarini_birlestir --kuru
    python -m talimatname.araclar.kacirma_aksiyonlarini_birlestir --evet

Yalnızca şu koşulları sağlayan aksiyonlar kapatılır:

* kaynağı `missed_run`,
* durumu `open`,
* kaynak kimliği **bir çalıştırmanın kimliği** (yani eski şema),
* ve aynı (şube, plan, gün) için yeni gruplanmış aksiyon **mevcut**.

Son koşul önemli: karşılığı olmayan bir kaydı kapatmak, takibi
sessizce düşürmek olurdu.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import UTC, datetime

from talimatname.api import bagimliliklar
from talimatname.api.app import configure_logging
from talimatname.domain.actions import action_id, missed_run_source
from talimatname.settings import get_settings

NOT = "Kaçırma aksiyonları gün bazında gruplandı; bu kayıt aynı günün tek satırında izleniyor."


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--kuru", action="store_true", help="Yazma, ne kapanacağını göster")
    ayristirici.add_argument("--evet", action="store_true", help="Gerçekten kapat")
    arg = ayristirici.parse_args(argv)

    configure_logging(get_settings().log_level)
    bagimliliklar._ilk_tur()
    aksiyonlar = bagimliliklar._aksiyon_deposu()
    planlar = bagimliliklar._plan_deposu()

    calistirmalar = {r.id: r for r in planlar.runs()}
    mevcut = {a.source_id for a in aksiyonlar.actions() if a.source == "missed_run"}

    devredilen = []
    for aksiyon in aksiyonlar.actions():
        if aksiyon.source != "missed_run" or aksiyon.status != "open":
            continue
        run = calistirmalar.get(aksiyon.source_id) if aksiyon.source_id else None
        if run is None:
            continue  # kaynağı çalıştırma değil: zaten yeni şema
        grup = missed_run_source(run.branch_id, run.plan_id, run.business_day)
        if action_id("missed_run", grup) == aksiyon.id or grup not in mevcut:
            continue  # kendisi grup kaydı, ya da karşılığı yok
        devredilen.append(aksiyon)

    print(f"devredilen kaçırma aksiyonu: {len(devredilen)}")
    for aksiyon in devredilen[:5]:
        print(f"  {aksiyon.title}")
    if len(devredilen) > 5:
        print(f"  … ve {len(devredilen) - 5} tane daha")

    if not arg.evet or arg.kuru:
        if not arg.kuru:
            print("uygulamak için: --evet")
        return 0

    an = datetime.now(UTC)
    for aksiyon in devredilen:
        aksiyonlar.save_action(replace(aksiyon, status="closed", close_note=NOT, closed_at=an))
    print(f"kapatıldı: {len(devredilen)}")
    return 0


if __name__ == "__main__":  # pragma: no cover - süreç girişi
    sys.exit(main())
