"""Yapılandırma kontrolleri (ADR-0014 md.12, ADR-0012).

İddia: **eksik yapılandırmayla üretim açılmaz.** Sessizce yerel diske
ya da geçici anahtara düşmek, kanıtın nerede durduğunu ve oturumların
ne kadar yaşadığını belirsiz bırakırdı.
"""

from __future__ import annotations

import pytest

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


def test_cors_jokeri_kabul_edilmez() -> None:
    with pytest.raises(RuntimeError, match="joker"):
        _ayar(cors_origins=["*"])
