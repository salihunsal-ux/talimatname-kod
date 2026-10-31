"""S3 uyumlu depolama adaptörü testleri (ADR-0012 md.4).

Kova taklit ediliyor (`moto`): adaptörün sözleşmesi — var olmayan
anahtarda `ObjectMissing`, yazılanın aynen geri gelmesi, silinenin
gitmesi — sağlayıcıdan bağımsız doğrulanıyor. Gerçek kovayla
(MinIO, yerli sağlayıcı) dumanı dağıtım işi koşuyor.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from talimatname.services.storage import ObjectMissing, S3ObjectStore, digest

KOVA = "talimatname-deneme"


@pytest.fixture
def kova() -> Iterator[S3ObjectStore]:
    from moto import mock_aws

    # moto kimlik arar: gerçek bir hesaba düşmesin diye sahte veriyoruz.
    onceki = {
        anahtar: os.environ.get(anahtar)
        for anahtar in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION")
    }
    os.environ.update(
        AWS_ACCESS_KEY_ID="deneme",
        AWS_SECRET_ACCESS_KEY="deneme",
        AWS_DEFAULT_REGION="us-east-1",
    )
    with mock_aws():
        # Uç nokta AWS'nin kendi adresi: `moto` yalnızca tanıdığı
        # konakları yakalıyor, uydurma bir alan adına gerçekten
        # bağlanmaya çalışıyor. Adaptör kodu yine aynı yoldan geçiyor
        # (endpoint_url verilmiş bir istemci).
        depo = S3ObjectStore(
            endpoint="https://s3.us-east-1.amazonaws.com",
            bucket=KOVA,
            access_key="deneme",
            secret_key="deneme",
        )
        depo.ensure_bucket()
        yield depo
    for anahtar, deger in onceki.items():
        if deger is None:
            os.environ.pop(anahtar, None)
        else:
            os.environ[anahtar] = deger


def test_yazilan_bayt_aynen_geri_gelir(kova: S3ObjectStore) -> None:
    icerik = b"\xff\xd8sahte-jpeg\xff\xd9"

    kova.put("evidence/r1/k1.jpg", icerik)

    assert kova.get("evidence/r1/k1.jpg") == icerik
    assert digest(kova.get("evidence/r1/k1.jpg")) == digest(icerik)


def test_olmayan_anahtar_object_missing(kova: S3ObjectStore) -> None:
    """Kanıt servisi bu hatayı "dosya depoya ulaşmadı"ya çeviriyor."""
    with pytest.raises(ObjectMissing):
        kova.get("evidence/yok.jpg")
    with pytest.raises(ObjectMissing):
        kova.size("evidence/yok.jpg")


def test_var_mi_ve_boyut(kova: S3ObjectStore) -> None:
    kova.put("evidence/r1/k1.jpg", b"12345")

    assert kova.exists("evidence/r1/k1.jpg") is True
    assert kova.exists("evidence/r1/yok.jpg") is False
    assert kova.size("evidence/r1/k1.jpg") == 5


def test_silme_sessizce_basarili(kova: S3ObjectStore) -> None:
    """Olmayanı silmek hata değil: temizlik yolu iki kez koşabilmeli."""
    kova.put("evidence/r1/k1.jpg", b"x")

    kova.delete("evidence/r1/k1.jpg")
    kova.delete("evidence/r1/k1.jpg")

    assert kova.exists("evidence/r1/k1.jpg") is False


def test_kova_iki_kez_hazirlanabilir(kova: S3ObjectStore) -> None:
    kova.ensure_bucket()  # ikinci çağrı: var olan kova hata vermemeli

    kova.put("evidence/r1/k1.jpg", b"x")
    assert kova.exists("evidence/r1/k1.jpg")


def test_on_imzali_yukleme_henuz_yok() -> None:
    """Sözleşme açık: baytlar hâlâ kendi uç noktamızdan geçiyor.

    Gerçek ön imzalı PUT ayrı bir iş; `presigned` True olsaydı kanıt
    servisi olmayan bir yolu kullanmaya kalkardı.
    """
    assert S3ObjectStore.presigned is False
