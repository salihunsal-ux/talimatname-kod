"""Demoyu tohum durumuna geri döndürür.

Demo herkese açık ve giriş kodu ekranda yazıyor (`DEMO_SHOW_OTP_CODE`),
yani numarayı bilen içeri girip personel maskeleyebilir, liste iptal
edebilir. Koruma eklemek yerine **geri alınabilir** yapmayı seçtik: bu
betik demoyu bilinen hâline döndürür.

    python -m talimatname.araclar.demo_sifirla --kuru   # ne silinecek, yazmadan
    python -m talimatname.araclar.demo_sifirla --evet   # uygula

Ne yapar:

1. İş verisini siler — çalıştırma, cevap, kanıt, aksiyon, bildirim,
   dışa aktarma işi — ve tohumun yazdığı her şeyi (şube, personel,
   şablon, plan) temizler.
2. Tohumu yeniden yazar: `python -m talimatname.seed` ile aynı veri.
3. Olay günlüğüne `demo.sifirlandi` yazar.

**Olay günlüğüne dokunmaz.** `audit_event` ve `audit_anchor` yerinde
kalıyor: günlük ekle-yalnız (göç 0006 uygulama rolüne yalnızca SELECT
ve INSERT veriyor) ve hash zinciri satır silmeyi kaldırmaz. Sonuç:
günlükte artık var olmayan nesnelere ait kayıtlar kalır. Bu kasıtlı —
"demo sıfırlandı" da olup bitenlerin bir parçası.

Üretimde koşmaz: `ENVIRONMENT=prod` ise reddeder. Tohum verisi
uydurmadır, gerçek kişi verisi yoktur (ADR-0003, ADR-0012 md.3).
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from sqlalchemy import text

from talimatname.api.app import configure_logging
from talimatname.infra.db.session import create_db_engine
from talimatname.seed import DEV_TENANT, ensure_tenant, seed
from talimatname.settings import get_settings

#: Silinecek tablolar, **yabancı anahtar sırasıyla** (çocuk önce).
#: `audit_event` ve `audit_anchor` listede yok ve olmayacak.
TABLOLAR: tuple[str, ...] = (
    "evidence",
    "answer",
    "notification",
    "action",
    "run",
    "export_job",
    "plan",
    "item",
    "section",
    "template_version",
    "template",
    "role_assignment",
    "app_user",
    "station",
    "branch",
    "region",
)

#: Hiçbir koşulda silinmez. Listeyi genişletirken buraya da bakın.
DOKUNULMAZ: frozenset[str] = frozenset({"audit_event", "audit_anchor", "tenant"})


def sayimlar(kiraci: object = DEV_TENANT) -> dict[str, int]:
    """Tablo başına satır sayısı; kuru çalıştırma bunu gösteriyor."""
    motor = create_db_engine(as_owner=True)
    sonuc: dict[str, int] = {}
    with motor.connect() as baglanti:
        for tablo in (*TABLOLAR, "audit_event"):
            satir = baglanti.execute(
                text(f"SELECT count(*) FROM {tablo} WHERE tenant_id = :k"),
                {"k": kiraci},
            ).scalar_one()
            sonuc[tablo] = int(satir)
    return sonuc


def temizle(kiraci: object = DEV_TENANT) -> int:
    """İş verisini siler, silinen satır sayısını döndürür."""
    assert not (set(TABLOLAR) & DOKUNULMAZ), "dokunulmaz tablo silme listesine girmiş"
    motor = create_db_engine(as_owner=True)
    toplam = 0
    with motor.begin() as baglanti:
        for tablo in TABLOLAR:
            sonuc = baglanti.execute(
                text(f"DELETE FROM {tablo} WHERE tenant_id = :k"),
                {"k": kiraci},
            )
            toplam += sonuc.rowcount or 0
    return toplam


def iz_birak(silinen: int) -> None:
    """Sıfırlamayı günlüğe yazar.

    Zincir kopmasın diye servis üzerinden: `prev_hash` doğru bağlansın.
    Yazamazsak iş düşmez ama sessiz de kalmaz.
    """
    try:
        from talimatname.api import bagimliliklar

        bagimliliklar._ilk_tur()
        bagimliliklar.izi_servisi().record(
            "demo.sifirlandi",
            object_type="kiraci",
            object_id=DEV_TENANT,
            after={"silinen_satir": silinen, "an": datetime.now(UTC).isoformat()},
        )
    except Exception as hata:  # pragma: no cover - günlük yazamamak işi düşürmez
        print(f"UYARI: olay günlüğüne yazılamadı: {type(hata).__name__}: {hata}")


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Demoyu tohum durumuna döndürür")
    ayristirici.add_argument("--kuru", action="store_true", help="Yazma, ne silineceğini göster")
    ayristirici.add_argument("--evet", action="store_true", help="Gerçekten sil (zorunlu)")
    arg = ayristirici.parse_args(argv)

    configure_logging(get_settings().log_level)
    ayar = get_settings()
    if not ayar.database_url:
        print("DATABASE_URL yok: api/.env içine yazın", file=sys.stderr)
        return 1
    if ayar.environment == "prod":
        print("Bu betik üretimde koşmaz (ENVIRONMENT=prod).", file=sys.stderr)
        return 1

    once = sayimlar()
    print("şimdiki durum:")
    for tablo, sayi in once.items():
        isaret = "  (korunur)" if tablo in DOKUNULMAZ else ""
        print(f"  {tablo:<18} {sayi:>6}{isaret}")

    if arg.kuru or not arg.evet:
        silinecek = sum(s for t, s in once.items() if t not in DOKUNULMAZ)
        print(f"\nsilinecek satır: {silinecek}; olay günlüğü ({once['audit_event']}) korunur")
        if not arg.kuru:
            print("uygulamak için: --evet")
        return 0

    silinen = temizle()
    yeni_kiraci = ensure_tenant()
    sayilar = seed()
    iz_birak(silinen)

    print(f"\nsilindi: {silinen} satır (olay günlüğü korundu)")
    print("tohum:", ", ".join(f"{k}={v}" for k, v in sayilar.items()))
    if yeni_kiraci:
        print("kiracı yeniden açıldı")
    print("geçmiş istenirse: python -m talimatname.araclar.demo_doldur --bitis <YYYY-AA-GG>")
    return 0


if __name__ == "__main__":  # pragma: no cover - süreç girişi
    sys.exit(main())
