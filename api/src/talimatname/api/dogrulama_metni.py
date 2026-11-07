"""Şema doğrulama hatalarının Türkçe karşılıkları.

Pydantic hata sözlüğünü ("type", "loc", "msg", "ctx") kullanıcıya
gösterilebilir bir cümleye çevirir. Zarf (RFC 9457) zaten Türkçeydi ama
alan sebebi ham geçiyordu: kullanıcı "İstek doğrulanamadı: Input should
be 'passed', 'failed'…" görüyordu.

Çeviri **tipe** bakar, mesaj metnine değil: Pydantic sürümü mesajı
değiştirdiğinde çeviri bozulmasın. Tanınmayan tip genel bir cümleye
düşer — İngilizceye değil.
"""

from __future__ import annotations

from typing import Any

#: Pydantic tipi → Türkçe cümle. `{...}` yer tutucuları `ctx`ten dolar.
METINLER: dict[str, str] = {
    "missing": "Bu alan zorunlu",
    "extra_forbidden": "Bu alan beklenmiyor",
    "json_invalid": "Gövde geçerli JSON değil",
    # tür
    "string_type": "Metin olmalı",
    "int_type": "Tam sayı olmalı",
    "int_parsing": "Tam sayı olmalı",
    "float_type": "Sayı olmalı",
    "float_parsing": "Sayı olmalı",
    "decimal_parsing": "Sayı olmalı",
    "bool_type": "Evet/hayır değeri olmalı",
    "bool_parsing": "Evet/hayır değeri olmalı",
    "list_type": "Liste olmalı",
    "dict_type": "Nesne olmalı",
    "model_attributes_type": "Nesne olmalı",
    # biçim
    "uuid_parsing": "Geçerli bir kimlik (UUID) olmalı",
    "uuid_type": "Geçerli bir kimlik (UUID) olmalı",
    "datetime_parsing": "Geçerli bir tarih-saat olmalı (ISO 8601)",
    "datetime_type": "Geçerli bir tarih-saat olmalı (ISO 8601)",
    "date_parsing": "Geçerli bir tarih olmalı (YYYY-AA-GG)",
    "date_type": "Geçerli bir tarih olmalı (YYYY-AA-GG)",
    "time_parsing": "Geçerli bir saat olmalı (SS:DD)",
    "url_parsing": "Geçerli bir adres olmalı",
    # sınır
    "string_too_short": "En az {min_length} karakter olmalı",
    "string_too_long": "En fazla {max_length} karakter olabilir",
    "too_short": "En az {min_length} öğe olmalı",
    "too_long": "En fazla {max_length} öğe olabilir",
    "greater_than": "{gt} değerinden büyük olmalı",
    "greater_than_equal": "En az {ge} olmalı",
    "less_than": "{lt} değerinden küçük olmalı",
    "less_than_equal": "En fazla {le} olabilir",
    "string_pattern_mismatch": "Biçim uygun değil",
}

#: Birden çok seçenekten biri beklenen hatalar: seçenekleri cümleye koyar.
SECENEKLI = {"literal_error", "enum"}

VARSAYILAN = "Değer geçerli değil"


def _secenekler(ctx: dict[str, Any]) -> str | None:
    """`ctx`teki beklenen değerleri "a, b ya da c" diye yazar."""
    beklenen = ctx.get("expected")
    if beklenen is None:
        return None
    if isinstance(beklenen, str):
        # Pydantic literal'leri "'a', 'b' or 'c'" diye verir; son
        # bağlacı Türkçeleştirmek yeterli, tırnaklar anlaşılır.
        return beklenen.replace(" or ", " ya da ")
    if isinstance(beklenen, (list, tuple)):
        degerler = [str(d) for d in beklenen]
        if len(degerler) == 1:
            return degerler[0]
        return ", ".join(degerler[:-1]) + " ya da " + degerler[-1]
    return str(beklenen)


def turkce(hata: dict[str, Any]) -> str:
    """Tek bir Pydantic hatasının Türkçe sebebi."""
    tip = str(hata.get("type", ""))
    ctx: dict[str, Any] = hata.get("ctx") or {}

    if tip in SECENEKLI:
        secenek = _secenekler(ctx)
        return f"Şunlardan biri olmalı: {secenek}" if secenek else VARSAYILAN

    # Alan doğrulayıcısının kendi Türkçe mesajı varsa o kazanır: bunlar
    # bizim yazdığımız cümleler, çevrilecek bir şey yok.
    if tip == "value_error":
        sebep = ctx.get("error")
        metin = str(sebep) if sebep is not None else ""
        return metin or VARSAYILAN

    kalip = METINLER.get(tip)
    if kalip is None:
        return VARSAYILAN
    try:
        return kalip.format(**ctx)
    except (KeyError, IndexError):
        # Beklenen bağlam gelmediyse yer tutucusuz hâline düşülür.
        return VARSAYILAN


def alan_adi(loc: tuple[Any, ...] | list[Any]) -> str:
    """Hata konumunu alan adına çevirir ("body" önekini atar)."""
    parcalar = [str(p) for p in loc]
    if parcalar and parcalar[0] in ("body", "query", "path", "header", "cookie"):
        parcalar = parcalar[1:]
    return ".".join(parcalar)
