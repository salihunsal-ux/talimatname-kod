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
./.venv/Scripts/python.exe -m uvicorn talimatname.api.app:create_app --factory --reload
```

- API: `http://127.0.0.1:8000/api/v1/health`
- Dokümantasyon: `http://127.0.0.1:8000/api/v1/docs`
- OpenAPI: `http://127.0.0.1:8000/api/v1/openapi.json`

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

## Kural motoru ve ortak fikstürler

`spec/fikstur/*.json` iki istemcinin ortak sözleşmesidir. `window.json` bugün 10 durum içeriyor (gece yarısını aşan pencere, kapalı gün, tatil, iki haftada bir, yaz saati ileri/geri alınan geceler, plan başlangıcından önce). Kural değişikliği fikstür değişikliği olmadan birleştirilmez.

İki karar fikstürde açıkça yazılı:

- **Süre ve tolerans geçen zamandır** (UTC üzerinden eklenir). Yerel saatte eklemek, yaz saati gecesinde pencereyi 0 ya da 120 dakikaya çevirirdi.
- **Kapanışa çıpalı pencere gece yarısından sonra başlıyorsa iş günü, vardiyanın başladığı gündür** (BR-01'in lafzında yok; sahada doğrulanacak).

Fikstürdeki `acik_sorular` listesi, motorun henüz karşılamadığı durumları taşır — şu an bir tane: saat bilgisini RRULE'den alan kurallar (`BYHOUR`, saatlik hijyen şablonu).

## Commit ve dal

Ürün deposuyla aynı kural: `feat/ST-123-kisa-ad`, Türkçe commit mesajı, `ST-123:` öneki, PR + CI yeşil + squash merge.
