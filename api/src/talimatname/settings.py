"""Yapılandırma: 12-factor, tipli, eksikse uygulama açılmaz (ADR-0014 md.12)."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["dev", "test", "staging", "prod"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    environment: Environment = "dev"
    log_level: str = "INFO"

    # Veritabanı: sağlayıcıdan bağımsız standart PostgreSQL URL'si (ADR-0012 md.4).
    # dev'de boş olabilir: saf alan testleri ve /health veritabanı istemez.
    database_url: str | None = None

    # Zaman yolculuğu yalnızca staging'de açılır, prod'da asla (02-repo).
    time_travel_enabled: bool = False

    # Kanıt dosyaları: S3 uyumlu uç nokta; dev'de yerel dizin adaptörü kullanılır.
    object_store_endpoint: str | None = None
    object_store_bucket: str | None = None
    object_store_access_key: str | None = None
    object_store_secret_key: str | None = None
    #: S3 imzası bölge ister; MinIO ve çoğu yerli sağlayıcı için fark
    #: etmiyor ama boş bırakılamıyor.
    object_store_region: str = "us-east-1"
    #: S3 yokken kanıtların yazıldığı yerel dizin. Üretimde
    #: kullanılmaz: tek makineye bağlı, yedeği ve şifrelemesi yok.
    evidence_dir: str = "var/evidence"
    #: Damgada kullanılacak yazı tipi (ST-040). Boşsa sunucudaki bilinen
    #: yollar denenir; Türkçe harfleri olan bir yazı tipi bulunamazsa
    #: damga basılmaz (bkz. services/imaging).
    stamp_font_path: str | None = None

    access_token_minutes: int = Field(default=30, ge=5, le=240)

    # Belirteç imzası (RS256). Üretimde zorunlu; geliştirmede boşsa
    # geçici anahtar üretilir ve uyarı yazılır.
    jwt_private_key: str | None = None
    jwt_public_key: str | None = None

    # Tarayıcıdan çağıran kaynaklar. Yalnızca burada yazılı olanlar;
    # joker (*) kullanılmaz — kimlik bilgisi taşıyan istekler için güvensiz.
    #: NoDecode: pydantic-settings karmaşık alanları varsayılan olarak
    #: JSON sanıyor; `CORS_ORIGINS=http://localhost:8080` yazan bir
    #: `.env` uygulamayı açılışta düşürüyordu. Çözüm aşağıdaki
    #: ayrıştırıcı: virgüllü liste de JSON dizisi de kabul.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Virgülle ayrılmış kaynak listesi (CORS_ORIGINS)",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _kaynak_listesi(cls, deger: object) -> object:
        """`a,b` ya da `["a","b"]` — ikisi de okunur, boşluklar atılır."""
        if not isinstance(deger, str):
            return deger
        metin = deger.strip()
        if not metin:
            return []
        if metin.startswith("["):
            return json.loads(metin)
        return [parca.strip() for parca in metin.split(",") if parca.strip()]

    @field_validator("jwt_private_key", "jwt_public_key", mode="before")
    @classmethod
    def _pem_satirlari(cls, deger: object) -> object:
        """`.env` tek satırlıktır: PEM'deki yeni satırlar `\\n` ile yazılır.

        Docker Compose'un `.env` çözümleyicisi çok satırlı değer kabul
        etmiyor; PEM gövdesini olduğu gibi yazmak dosyayı bozuyor. Bu
        yüzden `\\n` kaçışı burada gerçek yeni satıra çevriliyor —
        yoksa `.env.ornek`'teki tarif geçersiz bir anahtar üretirdi.
        """
        if isinstance(deger, str) and "\\n" in deger:
            return deger.replace("\\n", "\n")
        return deger

    @field_validator(
        "database_url",
        "object_store_endpoint",
        "object_store_bucket",
        "object_store_access_key",
        "object_store_secret_key",
        "jwt_private_key",
        "jwt_public_key",
        mode="before",
    )
    @classmethod
    def _bos_dize_none(cls, deger: object) -> object:
        """`.env` içinde `DATABASE_URL=` boş bırakılabilir: bu "tanımsız" demektir.

        Boş dizeyi tanımlı saymak, SQL moduna boş bağlantıyla girmek
        demek olurdu — sessiz ve kafa karıştırıcı bir hata.
        """
        if isinstance(deger, str) and not deger.strip():
            return None
        return deger

    @property
    def object_store_configured(self) -> bool:
        """S3 ayarlarının **tamamı** var mı.

        Yarım yapılandırma (uç nokta var, anahtar yok) sessizce yerel
        diske düşmemeli: üretimde kanıtın nerede durduğu belirsiz kalır.
        """
        return all(
            (
                self.object_store_endpoint,
                self.object_store_bucket,
                self.object_store_access_key,
                self.object_store_secret_key,
            )
        )

    def require_database_url(self) -> str:
        if not self.database_url:
            raise RuntimeError(
                "DATABASE_URL tanımlı değil. Veritabanı gerektiren uç noktalar ve "
                "göçler bu ayar olmadan çalışmaz (bkz. README · yerel ortam)."
            )
        return self.database_url

    def model_post_init(self, _: object) -> None:
        if any(o == "*" for o in self.cors_origins):
            raise RuntimeError("CORS_ORIGINS içinde joker (*) kabul edilmez")
        if self.environment == "prod":
            if self.time_travel_enabled:
                raise RuntimeError("TIME_TRAVEL_ENABLED prod'da açık olamaz")
            if not self.database_url:
                raise RuntimeError("prod ortamında DATABASE_URL zorunlu")
            if not (self.jwt_private_key and self.jwt_public_key):
                raise RuntimeError(
                    "prod ortamında JWT_PRIVATE_KEY ve JWT_PUBLIC_KEY zorunlu: "
                    "geçici anahtar üretimi yalnızca geliştirme içindir"
                )
            if not self.object_store_configured:
                raise RuntimeError(
                    "prod ortamında nesne depolama zorunlu (OBJECT_STORE_*): "
                    "yerel dizin tek makineye bağlı, yedeği ve şifrelemesi yok"
                )
        if any((self.object_store_endpoint, self.object_store_bucket)) and not (
            self.object_store_configured
        ):
            raise RuntimeError(
                "Nesne depolama yarım yapılandırılmış: OBJECT_STORE_ENDPOINT, "
                "_BUCKET, _ACCESS_KEY ve _SECRET_KEY birlikte verilir"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
