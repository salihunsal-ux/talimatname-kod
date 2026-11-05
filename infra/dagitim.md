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

## Deneme sürümü: erişilebilir ama gerçek verisiz

Pilottan önce ürünün ayakta ve telefondan erişilebilir olması gerekiyor:
denemeler, ekran turları, "şunu da görelim" soruları. O sürümde **gerçek
veri tutulmuyor** — şubeler, çalışanlar ve fotoğraflar tohum verisinden
geliyor.

Bunun pratik sonucu şu: **sağlayıcı ve ülke bu aşamada serbest.**
ADR-0003'ün "kanıt kovası Türkiye'de" şartını tetikleyen şey kişisel
veri; uydurma veride o şart yok. Yer kararı, gerçek şube verisi girdiği
gün verilir — ve aynı compose dosyası orada da kalkar.

Serbest olmayan tek şey, uyuyan makine. Zamanlayıcı dakikada bir tur
atmazsa liste açılmaz, hatırlatma gitmez, kaçırma yazılmaz (yukarı
bakın, ADR-0012 md.3). Aranan şey basit: Docker koşan, uykuya geçmeyen,
~2 vCPU / 4 GB bir makine ve A kaydı ona bakan bir alan adı. Alan adı
sertifika için gerekli — telefon tarayıcıları sertifikasız bir panele
kamera izni vermez, yani kanıt fotoğrafı akışı denenemez.

```bash
git clone <depo> && cd talimatname-kod
sudo bash infra/sunucu_hazirla.sh panel.ornek.com
```

Betik Docker'ı kurar, güvenlik duvarını kapatır ve `.env`'i üretir:
parolalar ile RS256 anahtarı **sunucuda** üretilip doğrudan dosyaya
yazılır, ekrana basılmaz. Gerisi yukarıdaki ilk kurulum adımları.

Deneme sürümünde:

- `ENVIRONMENT=staging` kalır; üretim katılığı (zorunlu anahtar, kapalı
  zaman yolculuğu) burada aranmaz, çünkü zaman yolculuğu denemenin
  kendisi için lazım.
- `tohum` **koşulur**. Üretimde koşulmaz (ADR-0003): aynı makinede hem
  uydurma hem gerçek şube olursa "bu kayıt gerçek mi" sorusu kalıcı
  hale gelir. Bu yüzden deneme makinesi pilot makinesi olmaz — pilot
  temiz bir kurulumla başlar.
- `DEMO_SHOW_OTP_CODE=true` gerekiyor. Giriş telefona gelen kodla ve
  SMS sağlayıcısı bağlı değil; bu ayar olmadan doğrulama kodunu kimse
  göremediği için demo kapısı kilitli kalır. Açıkken giriş tek faktöre
  iner — `/health` ve panelin Sistem durumu ekranı bunu yazıyor, prod'da
  ise ayar açılamıyor. Gerçek veri girilecek bir kurulumda kapalı.
- `TSA_URL` boş bırakılır: çıpalama kapalı, `/health` bunu söylüyor.
  Zaman damgası sağlayıcısı bir hukuk kararı, demo için gerekmiyor.
- Erişimi dar tutmak isterseniz güvenlik duvarında kaynak IP sınırı en
  ucuz çözüm; panelde ayrı bir "demo kapısı" yok.

### Saha istemcisini ayrı alan adında açmak

Merkez paneli ile saha istemcisi aynı pakette. Aynı kökende iki sekme
açarsanız **tek oturumu paylaşırlar**: tarayıcı deposu kaynağa bağlı,
yani aynı anda hem müdür hem personel olamazsınız ve uçtan uca akışı
denemek sürekli çıkış-giriş ister.

Çözüm ayrı paket değil **ayrı kaynak**: ikinci bir alan adı, aynı kap,
aynı `/srv`, aynı `/api`.

1. DNS: `saha.<alan>` için A kaydı, panelle aynı sunucuyu göstersin.
   Caddy sertifikayı ancak kayıt yayıldıktan sonra alabilir.
2. `.env`: `SAHA_ADRESI=saha.<alan>`
3. `docker compose up -d web`

Açılınca `saha.<alan>` doğrudan saha istemcisini veriyor — rol ne
olursa olsun; müdür de oradan girip personelin gördüğü ekranı görür.
Panel tarafı değişmiyor.

`SAHA_ADRESI` boşsa Caddy bu bloğu kap içinde yayımlanmamış bir porta
bağlar: dışarıdan erişilemez, sertifika istenmez, hiçbir şey değişmez.
Yerelde denemek için `saha.localhost:5173` yeter; tarayıcılar
`*.localhost` adlarını kendileri çözüyor, hosts dosyası gerekmiyor.

### Deneme sürümünü sınadıktan sonra toparlama

Denemede açılan şeyler kalıcıdır: `tohum` yalnızca bölge, şube,
istasyon, kullanıcı, şablon ve plan yazar — çalıştırma, aksiyon ve
bildirimleri **zamanlayıcı** üretir, onlara dokunmaz. Yani elle açılan
bir plan ya da "yapılmayacak" işaretlenen bir çalıştırma tohumu yeniden
koşturmakla geri gelmez.

Toparlarken iki kural:

1. **`audit_event`'e dokunulmaz.** Kayıt zinciri ürünün vaadi; silinen
   bir satır zinciri kırar. İz, geri alınan bir denemeyi de gösterir —
   doğrusu da budur, o deneme gerçekten yapıldı.
2. **SQL ile düzeltilen iş kaydı ize yazılmaz.** Uygulamanın kendi
   yolu yoksa (örneğin "yapılmayacak"ı geri alma eylemi yok) SQL tek
   çare; o zaman izle veritabanı arasında bilerek bir fark bırakılmış
   olur ve bu yazıya geçer.

Uygulamanın kendi kendini onardığı yerleri zorlamayın: çalıştırmayı
`missed`'e döndürmek yeter, eksik aksiyonu zamanlayıcı bir sonraki
turda açar (`sync_from_runs`, kimlik çalıştırmadan türüyor).

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
