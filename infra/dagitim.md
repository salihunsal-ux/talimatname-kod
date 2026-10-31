# Dağıtım: tek makinede tam yığın

Bu paket **sağlayıcıdan bağımsız**. Docker koşan herhangi bir sunucuda
aynı komutlarla kalkar: AB'de bir VPS, Türkiye'de bir bulut sunucu ya
da kendi makineniz. ADR-0012 md.4'ün "ortam değişikliği bir haftalık
iş olmalı" şartı böyle karşılanıyor — yazarak değil, aynı compose
dosyasını iki yerde koşturarak.

Ne nerede duruyor:

| Servis | Ne yapar | Üretimde |
|---|---|---|
| `web` (Caddy) | Paneli servis eder, `/api`'yi arkaya aktarır, sertifikayı alır | Aynı |
| `api` | HTTP uç noktaları | Aynı |
| `zamanlayici` | Pencere açılışı, hatırlatma, eskalasyon, sabah özeti, kanıt damgası | Aynı |
| `postgres` | Veritabanı | Sağlayıcının yönetilen PostgreSQL'i de olabilir |
| `minio` | S3 uyumlu kova (geliştirme/staging) | **Yerine sağlayıcının kovası**, servis kaldırılır |

**Zamanlayıcı ayrı bir servis ve kapatılamaz.** Ürünün zamana bağlı
yarısı orada: ayakta değilse liste açılmaz, hatırlatma gitmez,
kaçırma yazılmaz, damga basılmaz. "Uykuya geçen" ücretsiz katmanlar
bu yüzden uygun değil (ADR-0012 md.3).

## İlk kurulum

```bash
git clone <depo> && cd talimatname-kod
cp infra/.env.ornek .env
```

`.env` içinde doldurulacak dört şey var; ikisi parola, ikisi anahtar:

```bash
# Parolalar
openssl rand -base64 32          # POSTGRES_PASSWORD
openssl rand -base64 32          # OBJECT_STORE_SECRET_KEY

# Belirteç imzası (RS256)
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out ozel.pem
openssl rsa -in ozel.pem -pubout -out acik.pem
python3 -c 'import pathlib;print(pathlib.Path("ozel.pem").read_text().strip().replace(chr(10), chr(92)+"n"))'   # JWT_PRIVATE_KEY
python3 -c 'import pathlib;print(pathlib.Path("acik.pem").read_text().strip().replace(chr(10), chr(92)+"n"))'   # JWT_PUBLIC_KEY
rm ozel.pem acik.pem
```

PEM'ler **tek satıra** indirilip tırnaksız yazılıyor: Compose'un
`.env` çözümleyicisi çok satırlı değer kabul etmiyor. Uygulama `\n`
kaçışını okurken geri açıyor, yani anahtar ister tek satır ister
kasadan gelen gerçek satırlarla verilsin çalışır.

Anahtarı kaybetmek, herkesin oturumunu düşürmek demek — `.env`
yedeklenmeli ve depoya **girmemeli** (`.gitignore`'da).

```bash
docker compose build
docker compose up -d postgres minio
docker compose run --rm goc        # şema
docker compose run --rm tohum      # örnek veri — YALNIZCA staging
docker compose up -d api zamanlayici web
```

Panel: `http://sunucu:8080`. Alan adı verdiyseniz (`SITE_ADRESI`),
`WEB_PORT=80` ve `WEB_TLS_PORT=443` yapın; Caddy sertifikayı kendi
alır ve yeniler.

**Tohum verisi üretimde koşulmaz.** Uydurma şube ve kişilerle gerçek
veriyi karıştırmak, "bu kayıt gerçek mi" sorusunu kalıcı hale getirir
(ADR-0003).

## Sürüm geçişi

```bash
git pull
docker compose build
docker compose run --rm goc        # göç önce: yeni kod eski şemayı görmesin
docker compose up -d api zamanlayici web
```

Göç **elle ve ayrı**: uygulama açılışında otomatik göç, iki kapsayıcı
aynı anda kalktığında yarışır ve geri alınamaz bir şemayı sessizce
uygular (ADR-0014 md.11). Göçler ileri ve geri çalışıyor; CI her
koşuda ileri → geri → ileri sınıyor.

## Yedek ve geri yükleme

```bash
bash infra/yedek.sh            # veritabanı + kova, tarih damgalı
bash infra/geri-yukle.sh <dizin>
```

NFR-13: geri yükleme provası yılda iki kez **kayda geçer**. Yedeğin
alındığını görmek yetmez; geri yüklendiğini görmek gerekir.

## Üretime (Türkiye) geçerken değişenler

1. `OBJECT_STORE_*` sağlayıcının kovasını gösterir, `minio` servisi
   compose'dan çıkarılır. **Kova Türkiye'de olmalı** (ADR-0003):
   kanıt fotoğrafı kişisel veri sayılabilir.
2. `DATABASE_URL` sağlayıcının PostgreSQL'ini gösterir (ya da
   `postgres` servisi aynı makinede kalır; yedek sizin işiniz olur).
3. `ENVIRONMENT=prod`. Bu, ayarların katı kontrollerini açar:
   JWT anahtarları, veritabanı ve nesne depolama **zorunlu** olur,
   zaman yolculuğu kapanır, uygulama eksik yapılandırmayla açılmaz.
4. `SITE_ADRESI` gerçek alan adı, `WEB_PORT=80`, `WEB_TLS_PORT=443`.
5. Üretim anahtarları yalnızca üretim ortamının kasasında; staging ve
   CI ayrı setle çalışır (ADR-0012).

Başka kod değişikliği yok. Taşınabilirlik şartının anlamı bu.

## Doğrulama

CI'daki **Dağıtım** işi her commit'te temiz bir makinede şunu yapıyor:
imajları kurar, yığını kaldırır, göçü koşar, `/health`'in veritabanını
ve kovayı gördüğünü doğrular, panelin açıldığını, zamanlayıcının tur
attığını ve kanıt kovasına gerçekten yazılıp okunduğunu sınar.

Yani "benim makinemde çalışıyor" cümlesi bu pakette yok: her commit'te
sıfırdan bir makinede kalkıyor.
