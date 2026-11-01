"""Zincir kökünü elle çıpalama komutu (ST-103; FR-1302).

Çıpa normalde zamanlayıcı turunda, günde bir kez alınır. Bu komut iki
durum için var:

* **Kaçan gün.** Damga sunucusuna ulaşılamadığı bir günün ardından
  işletmeci kendi tetikler; beklemek o günü çıpasız bırakırdı.
* **İlk kurulum.** Sunucu yeni tanımlandığında ilk çıpa hemen alınsın.

    python -m talimatname.izi_cipala

Çıkış kodu 0: damga alındı. 1: alınamadı (sebep yazılır) ya da
çıpalama kapalı. Komut günlüğü **okumaz, değiştirmez**; yalnızca
zincirin o anki başını dışarıya tarihletir ve kaydı ekler.
"""

from __future__ import annotations

import sys

import structlog

from talimatname.api.app import configure_logging
from talimatname.api.bagimliliklar import cipa_servisi
from talimatname.settings import get_settings

log = structlog.get_logger("cipa")


def kosu() -> int:
    configure_logging(get_settings().log_level)
    servis = cipa_servisi()

    if not servis.enabled:
        print(
            "Çıpalama kapalı: TSA_URL tanımlı değil.\n"
            "Zincir yine tutuyor ama dış damga yok — kayıtları tek tek "
            "değiştirmek görünür, bütün zinciri baştan hesaplamak değil."
        )
        return 1

    cipa = servis.anchor_now()
    if cipa is None:
        print("Günlük boş: çıpalanacak kayıt yok.")
        return 0

    if cipa.state != "ok":
        print(f"Damga alınamadı: {cipa.error}")
        print("Kayıt yine de yazıldı — çıpasız bir gün, çıpalı sanılmasın.")
        return 1

    print(f"Çıpa alındı: sıra {cipa.sequence}, özet {cipa.chain_hash[:16]}…")
    print(f"Damga zamanı: {cipa.stamped_at}  ·  otorite: {cipa.tsa_name or '-'}")
    return 0


def main() -> None:  # pragma: no cover - giriş noktası
    sys.exit(kosu())


if __name__ == "__main__":  # pragma: no cover
    main()
