"""Nesne depolama portu (ST-039; FR-0606, FR-1305, ADR-0012 md.4).

Veritabanında yaptığımızın aynısı: **port ve adaptör**. Uygulama
katmanı "S3" bilmez, `ObjectStore` bilir. Geliştirmede yerel dizin,
üretimde S3 uyumlu bir kova — sağlayıcı kararı (ADR-0012) bu kodu
değiştirmeden verilebilsin diye.

Yükleme akışı iki adımlı (FR-0606):

1. Sunucu **yükleme izni** verir (ön imzalı URL ya da yerel adaptörde
   imzalı bir uç nokta). Dosya sunucunun belleğinden geçmez.
2. İstemci yüklemeyi bitirince sunucu **özeti doğrular**. Beyan edilen
   SHA-256 ile depodaki baytların özeti tutmuyorsa kanıt reddedilir.

İkinci adım olmadan birinci adım bir güvenlik açığıdır: istemcinin
"yükledim, özeti şu" demesine güvenmek, kanıtı beyana indirger.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Protocol


class ObjectMissing(Exception):
    """Depoda yok. Alan hatası değil: altyapı durumu."""


class ObjectStore(Protocol):
    """Kanıt dosyalarının saklandığı yer."""

    #: Ön imzalı yükleme destekleniyor mu? Yerel adaptörde hayır:
    #: istemci kendi uç noktamıza yükler.
    presigned: bool

    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def size(self, key: str) -> int: ...

    def delete(self, key: str) -> None: ...


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LocalObjectStore:
    """Geliştirme adaptörü: dosyalar bir dizinde durur.

    Üretimde kullanılmaz — tek makineye bağlıdır, yedeklemesi ve
    şifrelemesi yoktur. `/health` bunu `object_store_configured`
    alanıyla söylüyor.
    """

    presigned = False

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _yol(self, key: str) -> Path:
        # Anahtar sunucuda üretiliyor ama yine de dizin dışına çıkışı
        # engelliyoruz: tek bir hatalı anahtar tüm diski açardı.
        hedef = (self._root / key).resolve()
        kok = self._root.resolve()
        if not hedef.is_relative_to(kok):
            raise ValueError(f"Depo kökü dışında anahtar: {key}")
        return hedef

    def put(self, key: str, data: bytes) -> None:
        yol = self._yol(key)
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_bytes(data)

    def get(self, key: str) -> bytes:
        yol = self._yol(key)
        if not yol.is_file():
            raise ObjectMissing(key)
        return yol.read_bytes()

    def exists(self, key: str) -> bool:
        return self._yol(key).is_file()

    def size(self, key: str) -> int:
        yol = self._yol(key)
        if not yol.is_file():
            raise ObjectMissing(key)
        return yol.stat().st_size

    def delete(self, key: str) -> None:
        self._yol(key).unlink(missing_ok=True)

    def temizle(self) -> None:
        """Yalnızca testler için: kökü boşaltır."""
        shutil.rmtree(self._root, ignore_errors=True)
        self._root.mkdir(parents=True, exist_ok=True)


class S3ObjectStore:
    """S3 uyumlu kova adaptörü (ADR-0012 md.4).

    Sağlayıcıya özel SDK yok: MinIO (geliştirme), Turkcell nDepo ya da
    başka bir yerli sağlayıcı — hepsi aynı S3 API'si. Sağlayıcı
    değişince değişen tek şey ortam değişkenleri.

    `presigned` **şimdilik False**: istemci baytları hâlâ kendi
    uç noktamıza yüklüyor. Gerçek ön imzalı PUT (dosyanın sunucudan
    hiç geçmemesi) ayrı bir iş; yarım bir ikinci yükleme yolu açmak,
    iki yolun kurallarının ayrışmasına davetiye olurdu.
    """

    presigned = False

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
    ) -> None:
        import boto3
        from botocore.config import Config

        self._bucket = bucket
        self._istemci = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            # Yol tarzı adresleme: alt alan adı tarzı (bucket.host) her
            # sağlayıcıda ve MinIO'da çalışmıyor.
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def _yok_mu(self, hata: Exception) -> bool:
        kod = getattr(hata, "response", {}).get("Error", {}).get("Code", "")
        return kod in ("404", "NoSuchKey", "NotFound")

    def ensure_bucket(self) -> None:
        """Kova yoksa oluşturur. Geliştirme ve staging kolaylığı;
        üretimde kova sağlayıcı tarafında açılır ve bu çağrı yetkisizse
        sessizce geçilir."""
        from botocore.exceptions import ClientError

        try:
            self._istemci.head_bucket(Bucket=self._bucket)
        except ClientError:
            try:
                self._istemci.create_bucket(Bucket=self._bucket)
            except ClientError as hata:  # pragma: no cover - yetki/zaten var
                log_hatasi = getattr(hata, "response", {}).get("Error", {}).get("Code", "")
                if log_hatasi not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                    raise

    def put(self, key: str, data: bytes) -> None:
        self._istemci.put_object(Bucket=self._bucket, Key=key, Body=data)

    def get(self, key: str) -> bytes:
        from botocore.exceptions import ClientError

        try:
            yanit = self._istemci.get_object(Bucket=self._bucket, Key=key)
        except ClientError as hata:
            if self._yok_mu(hata):
                raise ObjectMissing(key) from hata
            raise
        govde: bytes = yanit["Body"].read()
        return govde

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._istemci.head_object(Bucket=self._bucket, Key=key)
        except ClientError as hata:
            if self._yok_mu(hata):
                return False
            raise
        return True

    def size(self, key: str) -> int:
        from botocore.exceptions import ClientError

        try:
            yanit = self._istemci.head_object(Bucket=self._bucket, Key=key)
        except ClientError as hata:
            if self._yok_mu(hata):
                raise ObjectMissing(key) from hata
            raise
        boyut: int = yanit["ContentLength"]
        return boyut

    def delete(self, key: str) -> None:
        self._istemci.delete_object(Bucket=self._bucket, Key=key)
