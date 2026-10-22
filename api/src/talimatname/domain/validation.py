"""Ortak alan doğrulaması: hata tipi ve metin temizleme.

Birden çok alan modülü (organizasyon, kullanıcı, şablon) aynı kuralları
kullanıyor; kopyalamak yerine tek yerde.
"""

from __future__ import annotations


class ValidationError(ValueError):
    """Alan doğrulama hatası. `field_name` sunum katmanında alan adına döner."""

    def __init__(self, field_name: str, message: str) -> None:
        super().__init__(message)
        self.field_name = field_name
        self.message = message


def clean_name(value: str, field_name: str, *, max_length: int = 80) -> str:
    """Baş/son boşlukları atar, aradaki tekrarlı boşlukları teke indirir."""
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValidationError(field_name, "Boş olamaz")
    if len(cleaned) > max_length:
        raise ValidationError(field_name, f"En fazla {max_length} karakter")
    return cleaned
