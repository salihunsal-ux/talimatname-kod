"""Yapılandırma: 12-factor, tipli, eksikse uygulama açılmaz (ADR-0014 md.12)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    access_token_minutes: int = Field(default=30, ge=5, le=240)

    # Tarayıcıdan çağıran kaynaklar. Yalnızca burada yazılı olanlar;
    # joker (*) kullanılmaz — kimlik bilgisi taşıyan istekler için güvensiz.
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Virgülle ayrılmış kaynak listesi (CORS_ORIGINS)",
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
