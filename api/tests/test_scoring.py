"""Puan ve sabit kural testleri (FR-0306, FR-0307, FR-0405)."""

from __future__ import annotations

from talimatname.domain.scoring import (
    ItemOutcome,
    evaluate,
    opens_action,
    requires_evidence,
)


def test_tc020_puan_yuzdesi() -> None:
    """TC-020: puan = geçen / puanlanan × 100."""
    sonuc = evaluate(
        [
            ItemOutcome("m1", "passed"),
            ItemOutcome("m2", "passed"),
            ItemOutcome("m3", "failed"),
            ItemOutcome("m4", "passed"),
        ]
    )
    assert sonuc.score_percent == 75
    assert sonuc.result == "failed"  # puan geçse de bir madde başarısız
    assert sonuc.scored_item_count == 4


def test_tc020_talimat_maddesi_puanlanmaz() -> None:
    sonuc = evaluate(
        [
            ItemOutcome("m1", "passed"),
            ItemOutcome("bilgi", "passed", scored=False),
        ]
    )
    assert sonuc.scored_item_count == 1
    assert sonuc.score_percent == 100
    assert sonuc.result == "passed"


def test_uygun_degil_puani_dusurmez() -> None:
    """Fritözü olmayan şube 'uygun değil' işaretler; puan 100 kalır."""
    sonuc = evaluate(
        [
            ItemOutcome("m1", "passed"),
            ItemOutcome("fritoz", "not_applicable"),
        ]
    )
    assert sonuc.score_percent == 100
    assert sonuc.result == "passed"


def test_yapilamadi_basarisiz_sayilir() -> None:
    sonuc = evaluate(
        [
            ItemOutcome("m1", "passed"),
            ItemOutcome("m2", "not_done"),
        ]
    )
    assert sonuc.score_percent == 50
    assert sonuc.result == "failed"


def test_tc023_kritik_madde_sonucu_belirler() -> None:
    """TC-023/FR-0307: kritik madde başarısızsa çalıştırma puandan bağımsız başarısız."""
    sonuc = evaluate(
        [ItemOutcome(f"m{i}", "passed") for i in range(9)]
        + [ItemOutcome("gaz_vanasi", "failed", critical=True)]
    )
    assert sonuc.score_percent == 90
    assert sonuc.result == "failed"
    assert sonuc.failed_critical_items == ("gaz_vanasi",)


def test_puanlanan_madde_yoksa_puan_none() -> None:
    sonuc = evaluate([ItemOutcome("bilgi", "passed", scored=False)])
    assert sonuc.score_percent is None
    assert sonuc.result == "passed"


def test_tc114_basarisiz_cevapta_kanit_zorunlu() -> None:
    """TC-114/FR-0405: başarısız ve yapılamadı cevaplarında fotoğraf + not zorunlu."""
    assert requires_evidence("failed", critical=False) is True
    assert requires_evidence("not_done", critical=False) is True
    assert requires_evidence("passed", critical=True) is False
    assert requires_evidence("not_applicable", critical=False) is False


def test_tc046_aksiyon_yalnizca_kritikte_acilir() -> None:
    """BR-08: v1'de otomatik aksiyonu kritik madde açar."""
    assert opens_action("failed", critical=True) is True
    assert opens_action("not_done", critical=True) is True
    assert opens_action("failed", critical=False) is False
    assert opens_action("passed", critical=True) is False
