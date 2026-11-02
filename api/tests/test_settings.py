"""Yapılandırma kontrolleri (ADR-0014 md.12, ADR-0012).

İddia: **eksik yapılandırmayla üretim açılmaz.** Sessizce yerel diske
ya da geçici anahtara düşmek, kanıtın nerede durduğunu ve oturumların
ne kadar yaşadığını belirsiz bırakırdı.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from talimatname.services import tokens
from talimatname.settings import Settings

TAM_KOVA = {
    "object_store_endpoint": "http://minio:9000",
    "object_store_bucket": "kanit",
    "object_store_access_key": "anahtar",
    "object_store_secret_key": "gizli",
}


def _ayar(**ek: object) -> Settings:
    # `.env` okunmasın: testin sonucu geliştiricinin makinesine bağlı olmamalı.
    return Settings(_env_file=None, **ek)  # type: ignore[arg-type]


def test_prod_veritabanisiz_acilmaz() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        _ayar(environment="prod")


def test_prod_anahtarsiz_acilmaz() -> None:
    """Geçici anahtar üretimi yalnızca geliştirme içindir: sunucu her
    yeniden başladığında bütün oturumlar düşerdi."""
    with pytest.raises(RuntimeError, match="JWT_PRIVATE_KEY"):
        _ayar(environment="prod", database_url="postgresql://x/y")


def test_prod_nesne_depolamasiz_acilmaz() -> None:
    """Yerel dizin tek makineye bağlı, yedeği ve şifrelemesi yok."""
    with pytest.raises(RuntimeError, match="nesne depolama"):
        _ayar(
            environment="prod",
            database_url="postgresql://x/y",
            jwt_private_key="a",
            jwt_public_key="b",
        )


def test_prod_tam_yapilandirmayla_acilir() -> None:
    ayar = _ayar(
        environment="prod",
        database_url="postgresql://x/y",
        jwt_private_key="a",
        jwt_public_key="b",
        **TAM_KOVA,
    )

    assert ayar.object_store_configured is True


def test_yarim_kova_her_ortamda_reddedilir() -> None:
    """Uç nokta var, anahtar yok: sessizce yerel diske düşmek, kanıtın
    nerede durduğunu belirsiz bırakırdı."""
    with pytest.raises(RuntimeError, match="yarım yapılandırılmış"):
        _ayar(environment="staging", object_store_endpoint="http://minio:9000")


def test_kovasiz_staging_yerel_dizine_duser() -> None:
    ayar = _ayar(environment="staging")

    assert ayar.object_store_configured is False
    assert ayar.evidence_dir


def test_prod_zaman_yolculugu_acik_olamaz() -> None:
    with pytest.raises(RuntimeError, match="TIME_TRAVEL"):
        _ayar(
            environment="prod",
            time_travel_enabled=True,
            database_url="postgresql://x/y",
            jwt_private_key="a",
            jwt_public_key="b",
            **TAM_KOVA,
        )


def test_prod_demo_modu_acik_olamaz() -> None:
    """Kodu yanıta koymak ikinci faktörü iptal eder: prod'da yasak."""
    with pytest.raises(RuntimeError, match="DEMO_SHOW_OTP_CODE"):
        _ayar(
            environment="prod",
            demo_show_otp_code=True,
            database_url="postgresql://x/y",
            jwt_private_key="a",
            jwt_public_key="b",
            **TAM_KOVA,
        )


def test_demo_modu_varsayilan_kapali() -> None:
    assert _ayar().demo_show_otp_code is False


def test_cors_jokeri_kabul_edilmez() -> None:
    with pytest.raises(RuntimeError, match="joker"):
        _ayar(cors_origins=["*"])


def test_pem_tek_satir_kacisi_cozulur() -> None:
    """`.env` tek satırlık: PEM `\\n` ile yazılıyor (bkz. infra/.env.ornek).

    Docker Compose'un `.env` çözümleyicisi çok satırlı değer kabul
    etmiyor. Kaçış çözülmezse anahtar geçerli PEM olmaz ve ilk
    oturum açışta patlar — bu test tarifi doğruluyor.
    """
    ozel, acik = tokens._gecici_anahtar()
    ayar = _ayar(
        jwt_private_key=ozel.replace(chr(10), "\\n"),
        jwt_public_key=acik.replace(chr(10), "\\n"),
    )

    assert ayar.jwt_private_key == ozel
    assert ayar.jwt_public_key == acik

    # Gerçek imza/çözme: kaçış çözülmüş anahtar kullanılabilir olmalı.
    belirtec = tokens.imzala(ayar, subject="u1", scope="oturum", ttl=timedelta(minutes=5))
    assert tokens.coz(ayar, belirtec, scope="oturum")["sub"] == "u1"


def test_pem_gercek_satirlarla_da_calisir() -> None:
    """Kasadan çok satırlı gelen anahtar (ör. sağlayıcı sırrı) bozulmamalı."""
    ozel, acik = tokens._gecici_anahtar()
    ayar = _ayar(jwt_private_key=ozel, jwt_public_key=acik)
    assert ayar.jwt_private_key == ozel


def test_cors_virgullu_ortam_degiskeninden_okunur(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`.env` örneklerindeki biçim bu: `CORS_ORIGINS=a,b`.

    pydantic-settings karmaşık alanları varsayılan olarak JSON sanıyor;
    bu biçim ayrıştırılamayınca uygulama açılışta düşüyordu (compose
    dumanında yakalandı).
    """
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:8080, https://panel.ornek.test")
    ayar = _ayar()
    assert ayar.cors_origins == ["http://localhost:8080", "https://panel.ornek.test"]


def test_cors_json_dizisi_de_okunur(monkeypatch: pytest.MonkeyPatch) -> None:
    """Eski biçimi kıran bir değişiklik yapmıyoruz."""
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:8080"]')
    assert _ayar().cors_origins == ["http://localhost:8080"]


def test_cors_bos_birakilabilir(monkeypatch: pytest.MonkeyPatch) -> None:
    """Panel API ile aynı kaynaktan servis edilirse CORS gerekmiyor."""
    monkeypatch.setenv("CORS_ORIGINS", "")
    assert _ayar().cors_origins == []
