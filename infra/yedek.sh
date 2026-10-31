#!/usr/bin/env bash
# Veritabanı ve kanıt kovasının yedeği (ADR-0012 md.5).
#
# İkisi birlikte alınır: veritabanı kanıtın kaydını, kova dosyasını
# tutuyor. Yalnızca birini yedeklemek, geri yüklendiğinde "kaydı var
# dosyası yok" demek — kanıtlı listenin en kötü hâli.
#
#   bash infra/yedek.sh [hedef-dizin]
set -euo pipefail

KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$KOK"

DAMGA="$(date +%Y%m%d-%H%M%S)"
HEDEF="${1:-yedek}/$DAMGA"
mkdir -p "$HEDEF"

echo "── Veritabanı ─────────────────────────────────────"
# --clean --if-exists: geri yükleme var olan şemanın üstüne yazabilsin.
docker compose exec -T postgres pg_dump \
  --username "${POSTGRES_USER:-talimatname_owner}" \
  --dbname "${POSTGRES_DB:-talimatname}" \
  --clean --if-exists --no-owner \
  > "$HEDEF/veritabani.sql"
echo "  $(wc -l < "$HEDEF/veritabani.sql") satır"

echo "── Kanıt kovası ───────────────────────────────────"
# MinIO istemcisi kapsayıcının içinde; sağlayıcının kovası için
# aynı komut uç nokta değiştirilerek kullanılır.
docker compose exec -T minio sh -c '
  mc alias set yerel http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" > /dev/null
  mc mirror --quiet yerel/'"${OBJECT_STORE_BUCKET:-talimatname-kanit}"' /tmp/yedek > /dev/null
  tar -cf - -C /tmp yedek
' > "$HEDEF/kanit.tar"
echo "  $(du -h "$HEDEF/kanit.tar" | cut -f1)"

echo "── Bitti ──────────────────────────────────────────"
echo "$HEDEF"
echo
echo "Geri yükleme provası yılda iki kez kayda geçer (NFR-13)."
echo "Yedeğin alındığını görmek yetmez; geri yüklendiğini görmek gerekir:"
echo "  bash infra/geri-yukle.sh $HEDEF"
