"""Zamanlayıcı süreci (ST-027).

Mimaride ayrı bir süreçtir (01-teknik-mimari `SCH`): API ile aynı kodu
paylaşır ama ayrı çalışır, böylece web trafiği zamanlayıcıyı
geciktirmez ve tersi.

    python -m talimatname.scheduler            # 60 sn'de bir tur
    python -m talimatname.scheduler --once     # tek tur (CI, elle)
    python -m talimatname.scheduler --interval 300

Üretimde bu döngü yerine sistem zamanlayıcısı (systemd timer, cron ya da
sağlayıcının işi) `--once` ile çağırabilir; iş idempotent olduğu için
iki yol da güvenlidir.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from types import FrameType

import structlog

from talimatname.api.app import configure_logging
from talimatname.api.bagimliliklar import zamanlayici_servisi
from talimatname.settings import get_settings

log = structlog.get_logger("scheduler")


class _Durum:
    """Kapatma bayrağı. Tur ortasında kesmeyiz: bayrak kalkar, tur bitince çıkarız."""

    durdur: bool = False


def _durduruldu() -> bool:
    """Bayrağı fonksiyonla okuyoruz: döngü koşulu her turda yeniden sorulur."""
    return _Durum.durdur


def _dur(signum: int, frame: FrameType | None) -> None:
    _Durum.durdur = True
    log.info("zamanlayici.durdurma_istendi", signal=signum)


def tek_tur() -> int:
    """Tek tur koşar; günlüğe özet yazar, kaçırılan sayısını döndürür."""
    sonuc = zamanlayici_servisi().tick()
    log.info(
        "zamanlayici.tur",
        olusturulan=sonuc.created,
        silinen=sonuc.deleted,
        kacirilan=sonuc.missed,
        sessiz=sonuc.quiet,
    )
    return sonuc.missed


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Talimatname zamanlayıcısı")
    ayristirici.add_argument("--once", action="store_true", help="tek tur koş ve çık")
    ayristirici.add_argument("--interval", type=int, default=60, help="saniye (varsayılan 60)")
    arg = ayristirici.parse_args(argv)

    configure_logging(get_settings().log_level)
    logging.captureWarnings(True)
    signal.signal(signal.SIGINT, _dur)
    signal.signal(signal.SIGTERM, _dur)

    if arg.once:
        tek_tur()
        return 0

    log.info("zamanlayici.basladi", interval=arg.interval)
    while not _durduruldu():
        try:
            tek_tur()
        except Exception:
            log.exception("zamanlayici.tur_hatasi")
        for _ in range(arg.interval):
            if _durduruldu():
                break
            time.sleep(1)
    log.info("zamanlayici.durdu")
    return 0


if __name__ == "__main__":  # pragma: no cover - süreç girişi
    sys.exit(main())
