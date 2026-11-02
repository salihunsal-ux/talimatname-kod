#!/usr/bin/env bash
# Temiz bir sunucuyu (Ubuntu 24.04) dağıtıma hazırlar.
#
#   sudo bash infra/sunucu_hazirla.sh panel.ornek.com   # alan adı varsa: 80/443 + TLS
#   sudo bash infra/sunucu_hazirla.sh                   # yoksa: IP:8080, sertifika yok
#
# Ne yapar: Docker'ı kurar, güvenlik duvarını kapatır, `.env`'i örnekten
# üretir ve parolalarla anahtarları **sunucuda** üretip doğrudan dosyaya
# yazar. Hiçbir sır ekrana basılmaz; kopyalanıp bir yere yapıştırılması
# gerekmez, çünkü yapıştırılan sır sohbette ve kabukta iz bırakır.
#
# Ne yapmaz: yığını kaldırmaz. Göçü ve tohumu siz koşturursunuz — tohum
# verisi üretimde koşulmamalı (ADR-0003), o kararı betik veremez.
set -euo pipefail

ALAN="${1:-}"
KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_DOSYA="$KOK/.env"
PORT="$([ -n "$ALAN" ] && echo 80 || echo 8080)"

[ "$(id -u)" -eq 0 ] || { echo "Root gerekiyor: sudo bash $0 ${ALAN}" >&2; exit 1; }

echo "== Docker =="
if ! command -v docker >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq docker.io docker-compose-v2 openssl python3 ufw
  systemctl enable --now docker
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose (v2) yok. Dağıtımınızda 'docker-compose-v2' paketi" >&2
  echo "bulunmuyorsa Docker'ın kendi deposunu kullanın: docs.docker.com/engine/install" >&2
  exit 1
fi

echo "== Güvenlik duvarı =="
# Bazı bulut imajları (OCI, kimi AWS AMI'leri) INPUT zincirini hazır
# kurallarla ve sonda bir REJECT ile veriyor. Böyle bir makinede ufw'yi
# açmak iki kural setini üst üste bindirir; var olan zincire eklemek
# daha az sürpriz.
#
# Not: Docker'ın yayınladığı portlar INPUT'a değil FORWARD/DOCKER
# zincirine düşüyor, yani kapsayıcılar bu kurallar olmadan da
# erişilebilir. Kurallar host üstünde koşan bir şey için duruyor.
PORTLAR=(22)
if [ -n "$ALAN" ]; then PORTLAR+=(80 443); else PORTLAR+=(8080); fi

if iptables -S INPUT 2>/dev/null | grep -q -- "-j REJECT"; then
  echo "hazır iptables zinciri bulundu (bulut imajı) — ona ekleniyor"
  for p in "${PORTLAR[@]}"; do
    KURAL=(-p tcp -m state --state NEW -m tcp --dport "$p" -j ACCEPT)
    iptables -C INPUT "${KURAL[@]}" 2>/dev/null || iptables -I INPUT 1 "${KURAL[@]}"
  done
  command -v netfilter-persistent >/dev/null && netfilter-persistent save >/dev/null
else
  # SSH önce: sırası kaçarsa kendimizi dışarıda bırakırız.
  ufw allow OpenSSH >/dev/null
  for p in "${PORTLAR[@]}"; do
    [ "$p" = 22 ] || ufw allow "$p/tcp" >/dev/null
  done
  ufw --force enable >/dev/null
fi
echo "açık: SSH + $([ -n "$ALAN" ] && echo '80/443' || echo '8080')"

echo "== .env =="
if [ -f "$ENV_DOSYA" ]; then
  echo ".env zaten var — dokunulmuyor (sırları ezmek oturumları düşürür)."
else
  GECICI="$(mktemp -d)"
  chmod 700 "$GECICI"
  trap 'rm -rf "$GECICI"' EXIT
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$GECICI/ozel.pem" 2>/dev/null
  openssl rsa -in "$GECICI/ozel.pem" -pubout -out "$GECICI/acik.pem" 2>/dev/null

  ORNEK="$KOK/infra/.env.ornek" \
  ENV_DOSYA="$ENV_DOSYA" \
  GECICI="$GECICI" \
  ALAN="$ALAN" \
  DB_PAROLA="$(openssl rand -base64 32)" \
  KOVA_PAROLA="$(openssl rand -base64 32)" \
  python3 - <<'PY'
import os
import pathlib

gecici = pathlib.Path(os.environ["GECICI"])
alan = os.environ["ALAN"]
adres = f"https://{alan}" if alan else "http://localhost:8080"


def tek_satir(ad: str) -> str:
    """PEM'i tek satıra indirir: Compose çok satırlı .env değeri okumuyor."""
    return gecici.joinpath(ad).read_text().strip().replace("\n", chr(92) + "n")


degerler = {
    "POSTGRES_PASSWORD": os.environ["DB_PAROLA"],
    "OBJECT_STORE_SECRET_KEY": os.environ["KOVA_PAROLA"],
    "JWT_PRIVATE_KEY": tek_satir("ozel.pem"),
    "JWT_PUBLIC_KEY": tek_satir("acik.pem"),
    "SITE_ADRESI": alan or ":80",
    "WEB_PORT": "80" if alan else "8080",
    "WEB_TLS_PORT": "443" if alan else "8443",
    "CORS_ORIGINS": adres,
    "PANEL_URL": adres,
}

satirlar = []
for satir in pathlib.Path(os.environ["ORNEK"]).read_text(encoding="utf-8").splitlines():
    ad = satir.split("=", 1)[0] if "=" in satir else ""
    satirlar.append(f"{ad}={degerler.pop(ad)}" if ad in degerler else satir)

if degerler:
    raise SystemExit(f".env.ornek'te bulunamayan anahtar: {sorted(degerler)}")

pathlib.Path(os.environ["ENV_DOSYA"]).write_text("\n".join(satirlar) + "\n", encoding="utf-8")
PY
  chmod 600 "$ENV_DOSYA"
  echo "yazıldı: $ENV_DOSYA (parolalar ve RS256 anahtarı üretildi, 600)"
fi

cat <<SON

== Sıra sizde ==

  cd $KOK
  docker compose build
  docker compose up -d postgres minio
  docker compose run --rm goc        # şema
  docker compose run --rm tohum      # örnek veri — YALNIZCA deneme/staging
  docker compose up -d api zamanlayici web

Sonra:
  curl -s localhost:$PORT/api/v1/health   # veritabanı + kova + çıpa durumu
  docker compose logs -f zamanlayici                  # tur atıyor mu

Panel: $([ -n "$ALAN" ] && echo "https://$ALAN" || echo "http://<sunucu-ip>:8080")
$([ -n "$ALAN" ] && echo "Caddy sertifikayı kendi alır; alan adının A kaydı bu makineyi göstermeli." || echo "Alan adı yok: sertifika da yok. Telefondan denemek için alan adı verin.")
SON
