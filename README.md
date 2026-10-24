# talimatname-kod

Talimatname'nin kod deposu: kanıtlı görev listesi (çok şubeli yeme-içme zincirleri için). Ürün dokümantasyonu ayrı depodadır (`Talimatname`): gereksinimler, kabul testleri, ekranlar ve kararlar orada; buradaki her modül oradaki bir FR'ye ve TC'ye bağlıdır.

Karar kayıtları: **ADR-0002** (yığın), **ADR-0005** (RRULE + pencere), **ADR-0012** (barındırma ve taşınabilirlik), **ADR-0013** (faz sırası: panel önce), **ADR-0014** (bu deponun düzeni ve kodlama standartları), **09-kod-sozlugu.md** (Türkçe terim → İngilizce tanımlayıcı).

## Düzen

```
api/     FastAPI · alan modeli ve kural motoru · göçler · testler
web/     React + TypeScript yönetim paneli
mobile/  Flutter (Faz B'de açılır — ADR-0013)
spec/    kural motoru JSON fikstürleri: backend ve mobil AYNI dosyaları geçer
infra/   compose, dağıtım, yedek betikleri, CI
```

Bağımlılık yönü içe doğru: `api → services → domain`, `infra → domain`. `domain` saf: I/O yok, çerçeve yok, **gerçek saat yok** (zaman parametre olarak geçer). Bu kuralın ihlali inceleme reddi sebebidir.

## Çalıştırma (api)

Windows PowerShell / Git Bash, Python 3.12:

```bash
cd api
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
cp .env.example .env
./.venv/Scripts/python.exe -m uvicorn talimatname.api.app:create_app --factory --reload --port 8010
```

- API: `http://127.0.0.1:8010/api/v1/health` · panel: `http://localhost:5173`
- Dokümantasyon: `http://127.0.0.1:8010/api/v1/docs`
- OpenAPI: `http://127.0.0.1:8010/api/v1/openapi.json`

**Port ve CORS:** panel geliştirmede API'yi **kendi kaynağından** çağırır; Vite `/api` isteklerini backend'e aktarır (`vite.config.ts`, hedef `VITE_API_TARGET`). Böylece geliştirmede CORS diye bir sorun yok ve backend portu değişince tek satır güncellenir. API'deki CORS ayarı (`CORS_ORIGINS`, joker `*` kabul edilmez) dağıtılmış ortamlar içindir.

Varsayılan backend portu **8010**'dur; bu makinede 8000 başka bir projeye ait ve 8010/8011 soketleri ölü süreçlerce tutulduğu için şu an **8020** kullanılıyor (`web/.env.local` → `VITE_API_TARGET`). Makine yeniden başlayınca varsayılana dönülebilir.

### Zamanlayıcı

Ayrı süreç (01-teknik-mimari `SCH`): ufuk üretimi ve toleransı dolan çalıştırmaların kapanışı.

```bash
cd api
./.venv/Scripts/python.exe -m talimatname.scheduler --once        # tek tur
./.venv/Scripts/python.exe -m talimatname.scheduler --interval 60 # döngü
```

İş **idempotenttir**: ikinci tur ne ekler ne siler. Üretimde döngü yerine sistem zamanlayıcısı `--once` ile çağırabilir. Geliştirmede zamanlayıcı süreci açık değilse panel ilk istekte bir tur atar (`api/bagimliliklar.py`), böylece pano boş kalmaz. `POST /api/v1/scheduler/tick` turu elle tetikler.

### Panel

```bash
cd web
npm install
npm run dev          # http://localhost:5173
npm run api:tipler   # OpenAPI değişince istemci tiplerini yeniden üret
npm test
```

Veritabanı **henüz gerekmiyor**: saf alan testleri ve `/health` PostgreSQL istemez. Veritabanı gerektiren uç noktalar `DATABASE_URL` ile açılır (ADR-0012 md.4: sağlayıcıdan bağımsız standart URL).

## Kapılar

```bash
cd api
./.venv/Scripts/python.exe -m ruff format . && ./.venv/Scripts/python.exe -m ruff check .
./.venv/Scripts/python.exe -m mypy
./.venv/Scripts/python.exe -m pytest --cov=talimatname.domain --cov-report=term-missing
```

Eşikler (ADR-0014 md.9-10): ruff temiz · `mypy --strict` temiz · kural kodunda kapsama **≥ %90** (şu an %98) · kabul testi numarası test adında (`test_tc025_...`).

Veritabanı isteyen testler `@pytest.mark.db` ile işaretlenir ve PostgreSQL yoksa atlanır; **sessiz atlama yok**, atlama sebebi yazılır.

## Veri: PostgreSQL (bellek içi adaptör hâlâ var)

Kalıcılık iki adaptörle çalışıyor ve seçim **tek yerde**: `DATABASE_URL` doluysa PostgreSQL, boşsa bellek içi (`api/bagimliliklar.py`). Servis katmanı, uç noktalar ve panel iki durumda da aynı.

```bash
cd api
cp .env.example .env            # DATABASE_URL satırını doldurun (infra/veritabani-kurulum.md)
./.venv/Scripts/python.exe -m alembic upgrade head     # şema + RLS + uygulama rolü
./.venv/Scripts/python.exe -m talimatname.seed         # tohum veri (idempotent)
```

**Çok kiracılılık veritabanında zorlanır** (ADR-0014 md.4):

- Her kiracı tablosunda `tenant_id`; 13 tabloda RLS politikası.
- Uygulama **sahip rolüyle çalışmaz**: bağlantı açılınca `SET ROLE talimatname_app` (bu rol `BYPASSRLS` almaz). Göçler sahip rolüyle koşar.
- Her iş birimi `SET LOCAL app.tenant_id` der. **Demezse hiçbir satır gelmez** — unutmak veri sızdırmaz, boş liste verir.
- `FORCE ROW LEVEL SECURITY`: yanlışlıkla sahip bağlantısıyla çalışıldığında da politika uygulanır.

Doğrulaması `tests/test_db.py` (TC-011): iki kiracı açılır, biri diğerinin şubesini kimliğini bilerek bile göremez. Veritabanı testleri `@pytest.mark.db` ile işaretli; `DATABASE_URL` yoksa **sebebi yazılarak** atlanır, diğer testler bellek içi koşar (`tests/conftest.py`).

Kurulum adımları: [infra/veritabani-kurulum.md](infra/veritabani-kurulum.md).

## Kimlik ve yetki

Giriş **telefon + tek kullanımlık kod** (OTP) ile; aynı mekanizma panelde ve mobilde kullanılacak (ST-004).

- Kod 6 hane, 5 dakika geçerli; 3 hatalı denemede 15 dakika blok, 60 saniye içinde yeniden gönderim yok (TC-009).
- Kodun kendisi **saklanmaz**: telefonla tuzlanmış HMAC-SHA256 özeti tutulur.
- Belirteç RS256 imzalı JWT. `JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY` boşsa dev'de geçici anahtar üretilir ve uyarı yazılır; staging/prod'da bu ayarlar zorunludur (uygulama açılmaz).
- **SMS sağlayıcısı henüz bağlı değil.** `/auth/request-code` bunu açıkça söyler (`delivered: false`) ve kodu yalnızca `ENVIRONMENT=dev` iken yanıta koyar. Sağlayıcı ST-067'de bağlanacak; o güne kadar panelde de "gönderildi" yazmıyoruz.

Yetki iki soruya ayrılmış ve ikisi de `api/guvenlik.py`de toplanıyor: **kim** (uç nokta hangi rolü ister) ve **nerede** (kapsam — `can_access` ile süzme). Kapsam belirteçten değil **kullanıcıdan** okunur: rol değişince ya da kullanıcı pasife alınınca elindeki belirteç eski yetkiyi taşımaz. Kapsam dışı kayıtta 404 değil **403** döner; şube kodları zincir içinde zaten bilinen bilgi.

Panelde de rol kapısı var (`web/src/api/yetki.ts`) ama bu **güvenlik değil nezakettir**: asıl denetim sunucuda. Arayüz yalnızca açılamayacak bölümü ve basılamayacak düğmeyi göstermiyor.

## Bildirim ve hatırlatma

Zamanlayıcı her turda iki sabit hatırlatmayı kuyruğa koyar (FR-0509): **pencere açılışında** ve **bitişe 30 dk kala**. Kuyruk idempotenttir — tur dakikada bir koşar, aynı dilim ikinci kez üretilmez.

Kanal bağımsız (FR-1007): servis `ChannelDriver` portunu kullanır; push (ST-046), SMS (ST-067) ve ileride WhatsApp birer sürücüdür, uygulama katmanı değişmez.

**Şu anda hiçbir sürücü bağlı değil.** Bunun görünür sonucu: gönderim denemesi `failed / surucu-yok` olarak kuyruğa yazılır, panelde "Bildirimler" sayfasında uyarıyla birlikte listelenir. Gönderilmemiş bildirimi gönderilmiş saymıyoruz — sahada kaybolan hatırlatmayı aramak, eksik entegrasyonu görmekten pahalı.

Sessiz saatler sabit, 23:00–07:00 yerel (FR-1004) ve **yalnızca yönetim bildirimlerine** uygulanır. Pencereye bağlı iş hatırlatması ötelenmez: kapanış listesi zaten gece yapılan iştir, hatırlatmasını sabaha atmak pencere kapandıktan sonra "30 dakika kaldı" demek olurdu.

### Eskalasyon ve sabah özeti

Merdiven v1'de **sabit** (FR-0912, BR-11); editörü v1.1:

| Tetik | Kime | Ne zaman |
|---|---|---|
| Kaçırılan liste | Şube müdürü | Anında |
| Kritik madde başarısız | Şube **ve** bölge müdürü | Anında; 10 dk içinde teslim yoksa SMS (FR-1008) |
| Gecikmiş aksiyon | Bölge müdürü, yönetici | Sabah özetinde |

İki kural kolay atlanır, ikisi de kodda:

- **Merdiven durur** (FR-0914): çalıştırma "yapılmayacak" olunca ya da aksiyon kapanınca bekleyen adımlar bastırılır (`suppressed`). Kapanmış işin ardından gelen bildirim güveni aşındırır.
- **Alıcı yoksa bir üst adıma** (FR-0915) ve bu **günlüğe yazılır** (`eskalasyon.alici_yok`). Sessizce düşürmek, eskalasyonun hiç olmamasıyla aynı şey. Tohumda Üsküdar'ın şube müdürü yok; kaçırma bildirimi bölge müdürüne çıkıyor ve kayıt düşüyor.

Sabah özeti (BR-27) her gün yerel 07:00: bölge müdürüne bölgesi, yöneticiye tüm hesap; önceki iş gününün kaçırılan/başarısız listeleri ve gecikmiş aksiyonları; push + e-posta. **Sorun yoksa da gider** ("her şey yolunda"): sessizlik, iyi haber ile bozuk entegrasyonu ayırt etmiyor. Bir kişiye günde bir özet; kimlik (kullanıcı, iş günü) ikilisinden türüyor.

Teslimat izi (FR-1005) `GET /notifications`: kanal, alıcı, zaman, deneme sayısı ve hata kodu. `sent` **kanala verildi** demektir; `delivered` ayrı bir durumdur ve kanalın geri bildirimiyle yazılır.

## Kanıt (ST-039, ST-049)

Ürünün iddiası "iş yapıldı" değil, **"iş yapıldığının kanıtı var"**. Akış üç çağrı (FR-0606):

```
POST /runs/{run}/answers/{answer}/evidence   → izin + yükleme adresi
PUT  {upload_url}                            → baytlar (sunucu belleğinden geçmez)
POST /evidence/{id}/complete                 → sunucu özeti kendisi hesaplar
GET  /evidence/{id}/url                      → 15 dk imzalı bağlantı (FR-1305)
```

İkinci ve üçüncü adımın **ayrı** olması kasıtlı: istemcinin "yükledim, özeti şu" demesine güvenmek kanıtı bir beyana indirger. Sunucu depodaki baytların SHA-256'sını kendisi hesaplar; tutmuyorsa kayıt **silinir** (bastırılmaz: tekillik kilidini tutsaydı bozuk bir yükleme doğru fotoğrafı sonsuza kadar yasaklardı).

**Tekillik** (FR-0614) hem serviste hem şemada: `(tenant_id, sha256)` tekil indeksi. Servis denetimi iki eşzamanlı yüklemede kaçabilir, indeks kaçmaz. Geçen haftanın fotoğrafını yeniden göndermek listeyi doldurmanın en kolay yolu olurdu.

**Bayraklar** (FR-0615) ölçüye dayanır ve **suçlama değil, incelemeye çağrıdır**: galeriden yükleme, konum şubeden 500 m'den uzak (BR-15 parametresi), konum yok, cihaz saati 10 dk'dan farklı, 72 saatten geç senk (cihaz kuyruğunun ömrü, FR-0706). Şubenin koordinatı tanımlı değilse "uzak" bayrağı **verilmez** — ölçüsüz bir şüphe işareti bayrağın anlamını boşaltır.

**Depolama** port/adaptör (ADR-0012 md.4): geliştirmede yerel dizin (`EVIDENCE_DIR`), üretimde S3 uyumlu kova. Sağlayıcı kararı bu kodu değiştirmeden verilebilir; üretim kovası Türkiye'de olmalı (fotoğraf kişisel veri sayılabilir).

## Senk: çevrimdışı kuyruk (ST-054)

Mobil çevrimdışı çalışır; liste doldurulurken de fotoğraf çekilirken de bağlantı olmayabilir. Sunucu yüzeyi iki çağrı (FR-0701, FR-0703):

```
GET  /sync/manifest   → ne indireceğim? 48 saatin çalıştırmaları, sürüm kimlikleri, sebep seti, sınırlar
POST /sync/batch      → kuyruğumu al: cevaplar + kanıt niyetleri (kanıt baytları ayrı)
```

**Manifest sürümün içeriğini değil kimliğini taşır.** Şablon sürümü yayınlandıktan sonra değişmez; cihaz `GET /template-versions/{id}` ile bir kez indirip süresiz önbelleğe alır. Manifest 15 dakikada bir tazelenirken şablon ağacını yeniden göndermek mobil veriyi boşa harcardı.

**`/sync/batch` 200 döner ve her kayıt kendi sonucunu taşır** (FR-0703). Tek bozuk kayıt yüzünden 4xx dönmek cihazın kuyruğunu sonsuza kadar tıkardı. Hata kayıt başına geliyor ve `retryable` cihaza ne yapacağını söylüyor: tek yeniden denenebilir alan hatası çalıştırma kilidi (30 dk'da düşer), gerisi belirlenimli — "pencere kapandı" bir daha denemekle düzelmez, cihaz kaydı bırakıp kullanıcıya söylemeli.

**Idempotans** (FR-0707): cevabın ve kanıtın kimliği **cihazda** üretilir. Aynı kuyruk iki kez gidince cevap güncellenir, kanıt `resumed` döner ve yükleme kaldığı yerden devam eder. Doğrulanmış kanıta ikinci yazma belirteci **verilmez** (BR-12 değişmezlik). Aynı fotoğraf başka bir kimlikle gelirse `duplicate`: cihaz kaydı bırakır, kullanıcı yeniden çeker.

**Saat düzeltmesi** (FR-0704, BR-13): cihaz senk anında kendi saatini söyler, sunucu farkı hesaplar. Fark **çekim zamanına** uygulanır; ham cihaz değeri ve fark kayıtta kalır, 10 dk'yı aşarsa kanıt bayrak alır. Olay zamanı (cevabın yazıldığı an) **sunucununkidir**: düzeltmeyi olay zamanına da uygulamak, saatini geri alan bir cihaza kapanmış pencereye yazma imkânı verirdi.

Kuyruk sınırlarını (500 kanıt / 72 saat, FR-0706) sunucu **söyler**, cihaz uygular: manifestteki `policy`. Sunucu tarafı zorlaması ST-060'ta.

**Yazma yolu ayrı değil:** senk cevabı `ExecutionService`e, kanıtı `EvidenceService`e indirir. Senk için ikinci bir yazma yolu yazmak, iki yolun kurallarının zamanla ayrışması demekti.

## Sürekli tümleştirme

`.github/workflows/kontrol.yml` üç iş koşuyor; üçü bağımsız, böylece tek koşuda bütün sorunlar görülüyor:

| İş | Ne yapıyor |
|---|---|
| **api** | ruff (biçim + lint) · mypy --strict · **göç ileri → geri → ileri** · tohum iki kez (idempotent olmalı) · pytest (veritabanı testleri dahil) · OpenAPI sözleşmesi güncel mi |
| **web** | prettier · eslint · tsc · vitest · build · üretilmiş istemci tipleri güncel mi |
| **fikstur** | `spec/*.json` geçerli JSON mu (iki istemcinin ortak sözleşmesi) |

Veritabanı testleri CI'da **sade bir `postgres:17` konteynerinde** koşuyor, sağlayıcıda değil. Bu bir kolaylık değil, bilinçli bir sınama: kod sağlayıcıya özel bir şey kullanmıyorsa herhangi bir PostgreSQL'de çalışmalı (ADR-0012 md.4). Çalışmadığı gün CI kırmızı yanar.

İki "güncel mi" adımı ADR-0014 md.10'un karşılığı: üretilmiş dosyalar (OpenAPI sözleşmesi, istemci tipleri) depoda duruyor ve CI bunları yeniden üretip karşılaştırıyor — **sözleşme kayması derleme hatasıdır**. `web/src/api/schema.ts` bu yüzden `.prettierignore` içinde: biçimini üretici belirler.

Aynı kontrolleri yerelde koşmak için:

```bash
bash scripts/kontrol.sh
```

## Kural motoru ve ortak fikstürler

`spec/fikstur/*.json` iki istemcinin ortak sözleşmesidir. `window.json` bugün 10 durum içeriyor (gece yarısını aşan pencere, kapalı gün, tatil, iki haftada bir, yaz saati ileri/geri alınan geceler, plan başlangıcından önce). Kural değişikliği fikstür değişikliği olmadan birleştirilmez.

İki karar fikstürde açıkça yazılı:

- **Süre ve tolerans geçen zamandır** (UTC üzerinden eklenir). Yerel saatte eklemek, yaz saati gecesinde pencereyi 0 ya da 120 dakikaya çevirirdi.
- **Kapanışa çıpalı pencere gece yarısından sonra başlıyorsa iş günü, vardiyanın başladığı gündür** (BR-01'in lafzında yok; sahada doğrulanacak).

Fikstürdeki `acik_sorular` listesi, motorun henüz karşılamadığı durumları taşır — şu an bir tane: saat bilgisini RRULE'den alan kurallar (`BYHOUR`, saatlik hijyen şablonu).

## Commit ve dal

Ürün deposuyla aynı kural: `feat/ST-123-kisa-ad`, Türkçe commit mesajı, `ST-123:` öneki, PR + CI yeşil + squash merge.
