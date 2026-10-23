# Geliştirme veritabanı kurulumu (Neon · ücretsiz katman)

Bu belge, geliştirme ortamının PostgreSQL'ini kurmak için **hesap sahibinin** yapacağı işleri anlatır. Kod tarafı (göçler, RLS politikaları, adaptörler) bağlantı dizesi hazır olduğunda yazılır.

Dayanak: [ADR-0012](../../Talimatname/docs/adr/0012-barindirma-saglayici-ve-ortamlar.md) md.2 — geliştirme ortamı ücretsiz ya da AB altyapıda olabilir, **tek şart gerçek kişisel veri olmaması**. Üretim Türkiye'de kalır.

## Kural: bu veritabanına ne girer, ne girmez

| Girer | Girmez |
|---|---|
| Tohum ve fikstür verisi (Kahve Durağı örnek zinciri, uydurma adlar) | Gerçek personel adı, telefonu, e-postası |
| Geliştirme sırasında elle üretilen test kayıtları | Pilot ya da müşteri verisi |
| Şablon, plan, çalıştırma örnekleri | Yüz içeren fotoğraf, gerçek kanıt dosyası |

Gerekçe teknik değil sözleşmesel: ücretsiz katmanda veri işleme sözleşmesi (DPA) imzalanamaz, SLA ve yedek garantisi yoktur. Pilot verisi Türkiye'deki üretim ortamına gider (ADR-0012 md.3).

## Adımlar

### 1. Hesap

1. <https://neon.tech> → **Sign up**.
2. GitHub ile giriş en hızlısı (ayrı parola yönetmezsiniz). E-posta ile de olur.
3. Plan seçimi çıkarsa **Free** kalsın. Kart istemez.

### 2. Proje

Yeni proje ekranında:

| Alan | Değer | Neden |
|---|---|---|
| Project name | `talimatname-dev` | Adından ne olduğu anlaşılsın |
| Postgres version | **17** (yoksa 16) | Üretimde de aynı ana sürüm kullanılacak |
| Cloud / Region | **AWS · Europe (Frankfurt) · eu-central-1** | ADR-0012: geliştirme AB'de olabilir; Türkiye'ye en yakın AB bölgesi |
| Database name | `talimatname` (ya da varsayılan `neondb`) | Fark etmez, bağlantı dizesinde geçecek |

**Create project** deyin.

### 3. Bağlantı dizesi

Proje açılınca **Connection string** kutusu gelir.

- Varsa **"Pooled connection"** anahtarını **kapatın** → doğrudan (direct/unpooled) bağlantıyı alın. Göçler ve oturum değişkenleri (RLS) doğrudan bağlantıda sorunsuz çalışır.
- Dizeyi **kopyalayın**. Şuna benzer:

```
postgresql://talimatname_owner:PAROLA@ep-xxxx-xxxx.eu-central-1.aws.neon.tech/talimatname?sslmode=require
```

> **Bu dizeyi sohbete yapıştırmayın.** İçinde parola var. Doğrudan aşağıdaki dosyaya yazın. Yanlışlıkla paylaşılırsa Neon konsolundan **Reset password** ile yenileyin.

### 4. `.env` dosyası

Dosya: `D:\Products\talimatname-kod\api\.env` (depoya girmez, `.gitignore`'da).

İçeriği tek satır:

```
DATABASE_URL=postgresql://talimatname_owner:PAROLA@ep-xxxx.eu-central-1.aws.neon.tech/talimatname?sslmode=require
```

Dikkat:

- Tırnak **yok**, `=` çevresinde boşluk **yok**.
- Not Defteri kullanıyorsanız "Farklı kaydet" → **Dosya türü: Tüm dosyalar**, ad: `.env` (yoksa `.env.txt` olur ve okunmaz).
- Kodlama **UTF-8**.

Örnek dosya zaten var: `api/.env.example` — kopyalayıp doldurabilirsiniz.

### 5. Doğrulama

Hesap sahibi isterse kendisi koşabilir (parolayı ekrana yazmaz):

```bash
cd D:/Products/talimatname-kod/api
./.venv/Scripts/python.exe -c "import os,psycopg;from dotenv import dotenv_values;u=dotenv_values('.env')['DATABASE_URL'];c=psycopg.connect(u);print('baglandi:',c.execute('select version()').fetchone()[0][:40]);print('rol olusturma izni:',c.execute(\"select rolcreaterole from pg_roles where rolname=current_user\").fetchone()[0])"
```

Beklenen çıktı iki satır: PostgreSQL sürümü ve `rol olusturma izni: True`.

**`rolcreaterole` False çıkarsa haber verin** — RLS için iki ayrı rol gerekiyor (uygulama rolü `BYPASSRLS` almaz, göç rolü ayrı). O durumda ya Neon'da rol izni açılır ya da sağlayıcı değişir.

### 6. Limitleri bir kez kontrol edin

Neon konsolunda **Settings → Usage**: ücretsiz katmanın depolama ve hesaplama saati sınırı. Ölçek notu: tohum verisiyle çalışıyoruz, sınırın yanına yaklaşmayız. Autosuspend açık kalsın (boşta durur, ilk istekte uyanır).

## Sonraki adım (kod tarafı)

`.env` hazır olduğunda yazılacaklar:

1. `infra/db/models.py` — SQLAlchemy 2.0 modelleri; her kiracı tablosunda `tenant_id`, UUID birincil anahtar, tarihsel tablolar yalnızca ekleme.
2. `infra/db/migrations/` — Alembic göçü: tablolar + **RLS politikaları** + iki rol; ileri ve geri test edilir.
3. Beş portun SQL adaptörü ve `api/bagimliliklar.py`'de anahtar (`DATABASE_URL` doluysa SQL, boşsa bellek içi).

İlk doğrulanacak kabul testi **TC-011 (kiracı yalıtımı)**: A hesabının belirteciyle B'nin satırları sorgulanır ve RLS'in kestiği görülür — uygulama katmanında değil, veritabanında.

## Vazgeçerseniz: yerel PostgreSQL

Bulut istemezseniz aynı iş yerel kurulumla da yürür: PostgreSQL 17 Windows kurulumu, `DATABASE_URL=postgresql://postgres:PAROLA@localhost:5432/talimatname`. Kod tarafında hiçbir fark olmaz (ADR-0012 md.4 taşınabilirlik şartı). Tek kaybınız CI'da dal başına veritabanı kolaylığı olur.
