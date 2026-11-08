"""Demo sıfırlama aracının bekçileri.

Araç demoyu tohum durumuna döndürüyor. İki şey asla kaymamalı: olay
günlüğü silinmemeli ve betik üretimde koşmamalı.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from talimatname.araclar import demo_sifirla
from talimatname.settings import Settings


def test_olay_gunlugu_silme_listesinde_degil() -> None:
    """`audit_event` ekle-yalnız (göç 0006); silme listesine giremez."""
    assert "audit_event" not in demo_sifirla.TABLOLAR
    assert "audit_anchor" not in demo_sifirla.TABLOLAR
    assert not set(demo_sifirla.TABLOLAR) & demo_sifirla.DOKUNULMAZ


def test_cocuk_tablolar_ebeveynden_once_siliniyor() -> None:
    """Yabancı anahtar sırası: cevap çalıştırmadan, çalıştırma plandan önce."""
    sira = demo_sifirla.TABLOLAR
    assert sira.index("answer") < sira.index("run") < sira.index("plan")
    assert sira.index("evidence") < sira.index("answer")
    assert sira.index("item") < sira.index("section") < sira.index("template_version")
    assert sira.index("role_assignment") < sira.index("app_user")
    assert sira.index("station") < sira.index("branch") < sira.index("region")


def test_prod_ortaminda_reddediyor(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Gerçek `Settings` prod'da kurulurken anahtar istiyor; buradaki soru
    # ayarın geçerliliği değil, betiğin prod'u reddetmesi.
    class _ProdAyar:
        database_url = "postgresql+psycopg://x/y"
        environment = "prod"
        log_level = "INFO"

    monkeypatch.setattr(demo_sifirla, "get_settings", _ProdAyar)

    assert demo_sifirla.main(["--evet"]) == 1
    assert "üretimde koşmaz" in capsys.readouterr().err


def test_veritabani_yoksa_reddediyor(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(demo_sifirla, "get_settings", lambda: Settings(database_url=None))

    assert demo_sifirla.main(["--evet"]) == 1
    assert "DATABASE_URL" in capsys.readouterr().err


def test_evet_yoksa_silmiyor(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Yıkıcı iş kazayla koşmasın: `--evet` olmadan yalnızca özet."""
    monkeypatch.setattr(
        demo_sifirla,
        "get_settings",
        lambda: Settings(database_url="postgresql+psycopg://x/y", environment="staging"),
    )
    monkeypatch.setattr(demo_sifirla, "sayimlar", lambda: {"run": 11, "audit_event": 500})

    def patlasin(*_: object) -> int:
        raise AssertionError("--evet olmadan silinmemeli")

    monkeypatch.setattr(demo_sifirla, "temizle", patlasin)

    assert demo_sifirla.main([]) == 0
    cikti = capsys.readouterr().out
    assert "--evet" in cikti
    assert "olay günlüğü (500) korunur" in cikti


def test_tohum_maskeli_kullaniciyi_diriltmiyor() -> None:
    """Maskeleme geri alınamaz; tohum onu geri yazmamalı (BR-22, FR-1310).

    Tohum idempotent diye her koşuşta adı ve telefonu üzerine yazsaydı,
    KVKK talebiyle silinmiş kişi verisi bir `python -m talimatname.seed`
    ile geri gelirdi.
    """
    from talimatname.domain.users import RoleAssignment, User
    from talimatname.infra.memory import sabit_id
    from talimatname.seed import korunur

    normal = User(
        id=sabit_id("kullanici:+905321110003"),
        full_name="Ayşe Şube",
        phone="+905321110003",
        assignments=(RoleAssignment("branch_manager", sabit_id("sube:KDK")),),
    )

    assert korunur(None) is False
    assert korunur(normal) is False
    assert korunur(normal.masked(datetime.now(UTC), 4821)) is True


@pytest.mark.db
def test_tohum_var_olan_surumun_uzerine_yazmiyor() -> None:
    """Yayınlanan sürüm bir daha değişmez (BR-18); çalıştırmalar ona bağlı.

    Tohum sürümü her koşuda yeniden yazıyordu: maddeleri silip
    kuruyordu. Cevabı olan bir veritabanında bu yabancı anahtar
    hatasıyla düşüyor (8 Kasım'da demoda oldu); düşmeseydi daha kötüsü
    olurdu — geçmiş cevapların bağlı olduğu soru değişirdi.

    Geliştirme kiracısında koşuyor: tohum zaten oranın verisi ve
    idempotent. Ayrı kiracı denenemiyor, bölge kimlikleri sabit.
    """
    from talimatname.seed import seed
    from talimatname.settings import get_settings

    if not get_settings().database_url:
        pytest.skip("veritabanı yok")

    sayilar = seed()

    assert sayilar["mevcut_surum_atlandi"] > 0, "sürümler yeniden yazılıyor"
