#!/usr/bin/env bash
# Yedeği geri yükler (ADR-0012 md.5, NFR-13 provası).
#
# **Üstüne yazar.** Prova için boş bir ortamda koşturun; üretimde
# yalnızca gerçekten kayıp varsa ve kararı veren kişi başındayken.
#
#   bash infra/geri-yukle.sh yedek/20261031-120000
set -euo pipefail

KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$KOK"

KAYNAK="${1:?kullanım: bash infra/geri-yukle.sh <yedek-dizini>}"
[ -f "$KAYNAK/veritabani.sql" ] || { echo "veritabani.sql yok: $KAYNAK"; exit 1; }
[ -f "$KAYNAK/kanit.tar" ] || { echo "kanit.tar yok: $KAYNAK"; exit 1; }

echo "DİKKAT: $KAYNAK yedeği mevcut verinin üstüne yazılacak."
read -r -p "Devam? (evet yazın) " onay
[ "$onay" = "evet" ] || { echo "vazgeçildi"; exit 1; }

echo "── Uygulama durduruluyor ──────────────────────────"
# Göç ve geri yükleme sırasında yazan bir süreç olmamalı.
docker compose stop api zamanlayici

echo "── Veritabanı ─────────────────────────────────────"
docker compose exec -T postgres psql \
  --username "${POSTGRES_USER:-talimatname_owner}" \
  --dbname "${POSTGRES_DB:-talimatname}" \
  --quiet < "$KAYNAK/veritabani.sql"

echo "── Kanıt kovası ───────────────────────────────────"
docker compose exec -T minio sh -c '
  rm -rf /tmp/yedek && tar -xf - -C /tmp
  mc alias set yerel http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" > /dev/null
  mc mb --ignore-existing yerel/'"${OBJECT_STORE_BUCKET:-talimatname-kanit}"' > /dev/null
  mc mirror --quiet --overwrite /tmp/yedek yerel/'"${OBJECT_STORE_BUCKET:-talimatname-kanit}"' > /dev/null
' < "$KAYNAK/kanit.tar"

echo "── Uygulama açılıyor ──────────────────────────────"
docker compose start api zamanlayici

echo
echo "Provayı kayda geçirin: tarih, süre, geri yüklenen yedek, sonuç."
echo "Kanıt sayısını panelden doğrulayın (Raporlar → Kanıt galerisi)."
