"""Pencere motoru testleri: ortak fikstür dosyasını koşar (ADR-0014 md.3).

Fikstür `spec/fikstur/window.json`; Faz B'de Flutter aynı dosyayı geçecek.
Buradaki testler veritabanı istemez.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

import pytest

from talimatname.domain.window import (
    Anchor,
    BranchCalendar,
    BusinessHours,
    WindowRule,
    windows,
)

FIKSTUR = Path(__file__).resolve().parents[2] / "spec" / "fikstur" / "window.json"


def _saat(metin: str) -> time:
    return time.fromisoformat(metin)


def _takvim(ham: dict[str, Any]) -> BranchCalendar:
    hours: dict[int, BusinessHours | None] = {}
    for gun, deger in ham["hours"].items():
        hours[int(gun)] = None if deger is None else BusinessHours(_saat(deger[0]), _saat(deger[1]))
    return BranchCalendar(
        timezone=ham["timezone"],
        hours=hours,
        closed_dates=frozenset(date.fromisoformat(d) for d in ham.get("closed_dates", [])),
    )


def _kural(ham: dict[str, Any]) -> WindowRule:
    anchor = ham.get("anchor")
    return WindowRule(
        recurrence=ham["recurrence"],
        starts_on=date.fromisoformat(ham["starts_on"]),
        duration_minutes=ham["duration_minutes"],
        start_time=_saat(ham["start_time"]) if ham.get("start_time") else None,
        anchor=Anchor(anchor["reference"], anchor["offset_minutes"]) if anchor else None,
        tolerance_minutes=ham.get("tolerance_minutes", 0),
    )


def _yukle() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    veri = json.loads(FIKSTUR.read_text(encoding="utf-8"))
    return veri["takvimler"], veri["durumlar"]


TAKVIMLER, DURUMLAR = _yukle()
KOSULACAK = [d for d in DURUMLAR if d["beklenen"] != "ATLANDI"]
ATLANAN = [d for d in DURUMLAR if d["beklenen"] == "ATLANDI"]


@pytest.mark.parametrize("durum", KOSULACAK, ids=[d["ad"] for d in KOSULACAK])
def test_tc025_pencere_fiksturleri(durum: dict[str, Any]) -> None:
    """TC-025/TC-032: pencere, gece yarısı, tolerans, kapalı gün ve yaz saati."""
    takvim = _takvim(TAKVIMLER[durum["takvim"]])
    kural = _kural(durum["kural"])
    ilk, son = (date.fromisoformat(g) for g in durum["aralik"])

    sonuc = windows(kural, takvim, ilk, son)

    assert len(sonuc) == len(durum["beklenen"]), durum["aciklama"]
    for pencere, beklenen in zip(sonuc, durum["beklenen"], strict=True):
        assert pencere.business_day == date.fromisoformat(beklenen["business_day"])
        assert pencere.window_start == datetime.fromisoformat(beklenen["window_start"])
        assert pencere.window_end == datetime.fromisoformat(beklenen["window_end"])
        assert pencere.tolerance_end == datetime.fromisoformat(beklenen["tolerance_end"])


def test_atlanan_fiksturler_belgelenmis() -> None:
    """Atlanan her fikstürün sebebi yazılı olmalı — sessiz atlama yok."""
    for durum in ATLANAN:
        assert durum.get("atlama_sebebi"), durum["ad"]


def test_tc034_pencere_durumu() -> None:
    """TC-034: pencere açılmadan önce / içinde / toleransta / kapandıktan sonra."""
    takvim = _takvim(TAKVIMLER["kadikoy"])
    kural = WindowRule(
        recurrence="FREQ=DAILY",
        starts_on=date(2026, 11, 2),
        start_time=time(8, 0),
        duration_minutes=60,
        tolerance_minutes=30,
    )
    (pencere,) = windows(kural, takvim, date(2026, 11, 2), date(2026, 11, 2))

    def an(saat: int, dakika: int) -> datetime:
        return datetime(2026, 11, 2, saat, dakika, tzinfo=UTC)

    assert pencere.state_at(an(4, 59)) == "before"
    assert pencere.state_at(an(5, 0)) == "open"
    assert pencere.state_at(an(5, 59)) == "open"
    assert pencere.state_at(an(6, 0)) == "tolerance"
    assert pencere.state_at(an(6, 29)) == "tolerance"
    assert pencere.state_at(an(6, 30)) == "closed"


def test_kural_dogrulamasi() -> None:
    """start_time ve anchor birlikte ya da ikisi birden eksik olamaz."""
    with pytest.raises(ValueError, match="start_time ya da anchor"):
        WindowRule(
            recurrence="FREQ=DAILY",
            starts_on=date(2026, 11, 2),
            duration_minutes=30,
        )
    with pytest.raises(ValueError, match="ikisi birlikte olmaz"):
        WindowRule(
            recurrence="FREQ=DAILY",
            starts_on=date(2026, 11, 2),
            duration_minutes=30,
            start_time=time(8, 0),
            anchor=Anchor("close", -60),
        )
    with pytest.raises(ValueError, match="duration_minutes pozitif"):
        WindowRule(
            recurrence="FREQ=DAILY",
            starts_on=date(2026, 11, 2),
            duration_minutes=0,
            start_time=time(8, 0),
        )


def test_ters_aralik_bos_doner() -> None:
    takvim = _takvim(TAKVIMLER["kadikoy"])
    kural = WindowRule(
        recurrence="FREQ=DAILY",
        starts_on=date(2026, 11, 2),
        start_time=time(8, 0),
        duration_minutes=60,
    )
    assert windows(kural, takvim, date(2026, 11, 5), date(2026, 11, 2)) == []


# --- iş kuralı sınırları (FR-0504, FR-0506) ---------------------------


def test_tolerans_tavani() -> None:
    """Saatlerce tolerans, "geç" ile "kaçırıldı" farkını siler."""
    with pytest.raises(ValueError, match="tolerance_minutes en çok 240"):
        WindowRule(
            recurrence="FREQ=DAILY",
            starts_on=date(2026, 11, 3),
            start_time=time(9, 0),
            duration_minutes=60,
            tolerance_minutes=241,
        )


def test_pencere_ve_tolerans_toplami_24_saati_asamaz() -> None:
    """Aşarsa çalıştırma ertesi gününkiyle çakışır."""
    with pytest.raises(ValueError, match="toplamı 1440"):
        WindowRule(
            recurrence="FREQ=DAILY",
            starts_on=date(2026, 11, 3),
            start_time=time(9, 0),
            duration_minutes=1440,
            tolerance_minutes=240,
        )


def test_sinirlarin_tam_ucu_gecerli() -> None:
    kural = WindowRule(
        recurrence="FREQ=DAILY",
        starts_on=date(2026, 11, 3),
        start_time=time(9, 0),
        duration_minutes=1200,
        tolerance_minutes=240,
    )

    assert kural.tolerance_minutes == 240
