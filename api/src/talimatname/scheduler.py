"""Zamanlayıcı süreci (ST-027).

Mimaride ayrı bir süreçtir (01-teknik-mimari `SCH`): API ile aynı kodu
paylaşır ama ayrı çalışır, böylece web trafiği zamanlayıcıyı
geciktirmez ve tersi.

    python -m talimatname.scheduler            # 60 sn'de bir tur
    python -m talimatname.scheduler --once     # tek tur (CI, elle)
    python -m talimatname.scheduler --interval 300

Döngü, her **başarılı** turdan sonra `--nabiz` dosyasına dokunur;
`--nabiz-denetle` o dosyanın tazeliğine bakıp çıkış kodu üretir. Kabın
sağlık kontrolü bunu çağırır: zamanlayıcı bir HTTP sunucusu değil, "port
açık mı" diye sorulamaz. Nabız yalnızca tur **bittiğinde** atıyor, yani
sürekli hata veren ya da takılmış bir döngü sağlıklı görünmüyor.

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
from datetime import UTC, datetime
from pathlib import Path
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


def nabiz_yaz(yol: Path, an: datetime | None = None) -> None:
    """Tur bitti işareti. Yazılamıyorsa tur düşmez, uyarı kalır."""
    try:
        yol.write_text((an or datetime.now(UTC)).isoformat(), encoding="utf-8")
    except OSError as hata:
        log.warning("zamanlayici.nabiz_yazilamadi", yol=str(yol), hata=str(hata))


def nabiz_yasi(yol: Path, an: datetime | None = None) -> float | None:
    """Son turun üzerinden geçen saniye; dosya yoksa ya da okunamıyorsa None."""
    try:
        yazilan = datetime.fromisoformat(yol.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if yazilan.tzinfo is None:
        yazilan = yazilan.replace(tzinfo=UTC)
    return ((an or datetime.now(UTC)) - yazilan).total_seconds()


def nabiz_denetle(yol: Path, azami: float, an: datetime | None = None) -> int:
    """Sağlık kontrolünün çıkış kodu: 0 sağlıklı, 1 değil."""
    yas = nabiz_yasi(yol, an)
    if yas is None:
        print(f"nabız yok: {yol}", file=sys.stderr)
        return 1
    if yas > azami:
        print(f"nabız bayat: {yas:.0f} sn (azami {azami:.0f})", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Talimatname zamanlayıcısı")
    ayristirici.add_argument("--once", action="store_true", help="tek tur koş ve çık")
    ayristirici.add_argument("--interval", type=int, default=60, help="saniye (varsayılan 60)")
    ayristirici.add_argument("--nabiz", type=Path, help="her turdan sonra dokunulacak dosya")
    ayristirici.add_argument(
        "--nabiz-denetle", type=Path, help="nabzın tazeliğine bak ve çık (sağlık kontrolü)"
    )
    ayristirici.add_argument(
        "--azami", type=float, default=200.0, help="nabız kaç saniyeye kadar taze sayılır"
    )
    arg = ayristirici.parse_args(argv)

    # Denetim ayrı bir süreç: ne veritabanına bağlanır ne günlük kurar,
    # çünkü sağlık kontrolü saniyede bir koşabilir.
    if arg.nabiz_denetle is not None:
        return nabiz_denetle(arg.nabiz_denetle, arg.azami)

    configure_logging(get_settings().log_level)
    logging.captureWarnings(True)
    signal.signal(signal.SIGINT, _dur)
    signal.signal(signal.SIGTERM, _dur)

    if arg.once:
        tek_tur()
        if arg.nabiz is not None:
            nabiz_yaz(arg.nabiz)
        return 0

    log.info("zamanlayici.basladi", interval=arg.interval)
    while not _durduruldu():
        try:
            tek_tur()
        except Exception:
            # Nabız atmıyor: üst üste hata veren döngü sağlıklı değil.
            log.exception("zamanlayici.tur_hatasi")
        else:
            if arg.nabiz is not None:
                nabiz_yaz(arg.nabiz)
        for _ in range(arg.interval):
            if _durduruldu():
                break
            time.sleep(1)
    log.info("zamanlayici.durdu")
    return 0


if __name__ == "__main__":  # pragma: no cover - süreç girişi
    sys.exit(main())
