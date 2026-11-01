"""Zincir doğrulama komutu (ST-100; FR-1304, TC-101).

İç araç: olay günlüğünün hash zincirini baştan hesaplar ve kırılma
varsa **nerede** olduğunu söyler. Ekranı v1.1 (FR-1303); v1'de
denetim sorusunun cevabı bu komut.

Zincirin yanında **çıpalar** da sınanıyor (FR-1302): dış zaman
damgası alınmış kayıtlar hâlâ aynı mı, damga hâlâ o özeti mi
taşıyor? Zincir tek başına "kayıtlar tek tek değişmemiş" der;
çıpa, "o tarihten önceki geçmiş baştan yazılmamış" der.

    python -m talimatname.izi_dogrula
    python -m talimatname.izi_dogrula --gun 30        # son 30 gün
    python -m talimatname.izi_dogrula --nesne <uuid>  # tek kaydın izi

Çıkış kodu 0: zincir bütün. 1: kırılma var — izleme ve CI bunu
okuyabilsin diye metin değil çıkış kodu konuşuyor.

Komut **yalnızca okur**. Günlüğü "onarmak" diye bir iş yok: onarılmış
bir denetim izi, denetim izi değildir.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog

from talimatname.api.app import configure_logging
from talimatname.api.bagimliliklar import cipa_servisi, izi_servisi
from talimatname.settings import get_settings

log = structlog.get_logger("izi")


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    ayristirici = argparse.ArgumentParser(
        prog="python -m talimatname.izi_dogrula",
        description="Olay günlüğü hash zincirini doğrular (FR-1304).",
    )
    ayristirici.add_argument(
        "--gun", type=int, default=None, help="Yalnızca son N günü doğrula (varsayılan: tümü)"
    )
    ayristirici.add_argument(
        "--nesne", type=str, default=None, help="Tek bir nesnenin izini yazdır (UUID)"
    )
    ayristirici.add_argument(
        "--sinir", type=int, default=50_000, help="En çok kaç olay okunur (varsayılan 50.000)"
    )
    ayristirici.add_argument(
        "--cipasiz", action="store_true", help="Yalnızca zinciri doğrula, çıpalara bakma"
    )
    return ayristirici.parse_args(argv)


def kosu(argv: list[str] | None = None) -> int:
    secenek = _args(argv)
    configure_logging(get_settings().log_level)
    servis = izi_servisi()

    if secenek.nesne:
        for olay in servis.for_object(UUID(secenek.nesne)):
            print(
                f"{olay.sequence:>6}  {olay.at.isoformat()}  {olay.event_type:<24} "
                f"{olay.ip or '-':<16} {olay.hash[:12]}"
            )
        return 0

    since = datetime.now(UTC) - timedelta(days=secenek.gun) if secenek.gun else None
    rapor = servis.verify(since=since, limit=secenek.sinir)

    if rapor.checked == 0:
        print("Günlük boş: doğrulanacak olay yok.")
        return 0

    print(f"{rapor.checked} olay doğrulandı (sıra {rapor.first_sequence}–{rapor.last_sequence}).")
    cikis = 0
    if rapor.intact:
        print("Zincir bütün.")
    else:
        print(f"ZİNCİR KIRIK: {len(rapor.breaks)} kayıtta sorun var.")
        for kirik in rapor.breaks:
            print(f"  sıra {kirik.sequence}  {kirik.event_id}  {kirik.reason}")
        cikis = 1

    if not secenek.cipasiz:
        cikis = max(cikis, _cipalar())
    return cikis


def _cipalar() -> int:
    """Çıpa raporu. Zincirden **ayrı** bir soru, ayrı yazılıyor.

    Çıpa yoksa bu bir hata değil ama sessiz de geçilmiyor: dış damga
    olmadan zincirin neyi gösterip neyi göstermediği yazılıyor.
    """
    servis = cipa_servisi()
    if not servis.enabled:
        print("Çıpalama kapalı (TSA_URL yok): zincir yalnızca tek tek değişiklikleri gösterir.")
        return 0

    rapor = servis.verify()
    if rapor.checked == 0:
        print("Henüz çıpa yok: 'python -m talimatname.izi_cipala' ile ilki alınabilir.")
        return 0

    print(f"{rapor.checked} çıpa sınandı; en yenisi {rapor.last_at}.")
    if rapor.intact:
        print("Çıpalar tutuyor: damgalanan kökler hâlâ aynı.")
        return 0

    print(f"ÇIPA TUTMUYOR: {len(rapor.problems)} çıpada sorun var.")
    for sorun in rapor.problems:
        print(f"  sıra {sorun.sequence}  {sorun.anchor_id}  {sorun.reason}")
    return 1


def main() -> None:  # pragma: no cover - giriş noktası
    sys.exit(kosu())


if __name__ == "__main__":  # pragma: no cover
    main()
