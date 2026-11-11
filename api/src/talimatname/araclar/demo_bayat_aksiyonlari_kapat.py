"""Çalıştırması sonradan tamamlanmış kaçırma aksiyonlarını kapatır (demo).

Aksiyon geri alınmaz (BR-10): kaçırma yaşandıysa kayıt açılır ve notla
kapanır. Üretimde bu doğrudur, çünkü kaçırılan bir liste geriye dönük
doldurulamaz (BR-03).

Demoda öyle değil: `demo_doldur` servisin saatini çalıştırmanın
penceresine çekerek geçmişi dolduruyor. Doldurduğu çalıştırmaların
**aksiyonları açık kalıyor** ve listede bir ay önceki "yapılmadı"
kayıtları birikiyor — demoda 13 kaçık çalıştırmaya karşılık 150 açık
aksiyon vardı.

Bu betik yalnızca **karşılığı kalmamış** olanları kapatır: kaynağına
bakar, o çalıştırma ya da o (şube, plan, iş günü) grubu hâlâ kaçıksa
**dokunmaz**. Yani gerçekten kaçırılmış listeler açık kalır.

    python -m talimatname.araclar.demo_bayat_aksiyonlari_kapat --kuru
    python -m talimatname.araclar.demo_bayat_aksiyonlari_kapat --evet

Üretimde koşmaz (`ENVIRONMENT=prod`): orada böyle bir bayatlama
olmuyor ve toplu kapatma iş kaydına müdahale olurdu.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import UTC, datetime

from talimatname.api import bagimliliklar
from talimatname.api.app import configure_logging
from talimatname.domain.actions import missed_run_source
from talimatname.settings import get_settings

NOT = "Liste sonradan tamamlandı (demo geçmişi dolduruldu); kaçırma kaydı güncel değil."


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Bayat kaçırma aksiyonlarını kapatır")
    ayristirici.add_argument("--kuru", action="store_true", help="Yazma, ne kapanacağını göster")
    ayristirici.add_argument("--evet", action="store_true", help="Gerçekten kapat")
    arg = ayristirici.parse_args(argv)

    configure_logging(get_settings().log_level)
    if get_settings().environment == "prod":
        print("Bu betik üretimde koşmaz (ENVIRONMENT=prod).", file=sys.stderr)
        return 1

    bagimliliklar._ilk_tur()
    aksiyonlar = bagimliliklar._aksiyon_deposu()
    planlar = bagimliliklar._plan_deposu()

    kacik = [r for r in planlar.runs() if r.status == "missed"]
    kacik_run = {r.id for r in kacik}
    kacik_grup = {missed_run_source(r.branch_id, r.plan_id, r.business_day) for r in kacik}

    bayat = [
        a
        for a in aksiyonlar.actions()
        if a.source == "missed_run"
        and a.status == "open"
        and a.source_id is not None
        and a.source_id not in kacik_run
        and a.source_id not in kacik_grup
    ]

    print(f"hâlâ kaçık çalıştırma: {len(kacik)}")
    print(f"bayat kaçırma aksiyonu: {len(bayat)}")
    for aksiyon in bayat[:5]:
        print(f"  {aksiyon.title}")
    if len(bayat) > 5:
        print(f"  … ve {len(bayat) - 5} tane daha")

    if not arg.evet or arg.kuru:
        if not arg.kuru:
            print("uygulamak için: --evet")
        return 0

    an = datetime.now(UTC)
    for aksiyon in bayat:
        aksiyonlar.save_action(replace(aksiyon, status="closed", close_note=NOT, closed_at=an))
    print(f"kapatıldı: {len(bayat)}")
    return 0


if __name__ == "__main__":  # pragma: no cover - süreç girişi
    sys.exit(main())
