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
