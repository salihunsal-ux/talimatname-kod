# Saha istemcisi (Flutter)

Personelin listeyi doldurduğu uygulama. Panel (`web/`) yöneticiler
için; burası şubede, telefonda, çoğu zaman **zayıf bağlantıyla**
çalışır.

Bugünkü hâli: giriş → bugünün listeleri → **liste doldurma** ve
çevrimdışı kuyruk. Kanıt fotoğrafı henüz yok (Spike C).

## Hedefler

| Hedef | Durum | Not |
|---|---|---|
| Android | **asıl hedef** | `flutter build apk` |
| Web | kısmen; yalnızca geliştirme | Giriş ve liste ekranı çalışır. **Çevrimdışı kuyruk açılmıyor** (aşağıya bakın). Dağıtılmaz: tarayıcıda güvenli depo yok, belirteç localStorage'a düşer |
| iOS | **yok** | macOS olmadan derlenemez; ayrı karar (ADR-0013, 12 Kasım eki) |

## Çalıştırma

API adresi derleme zamanında veriliyor. Varsayılan **yerel** API:
demoya kazara yazmamak için adres açıkça verilir.

```sh
flutter run -d chrome --web-port 5000 \
  --dart-define=API_BASE=http://127.0.0.1:8010/api/v1
```

Tarayıcıda koşarken API'nin **CORS**'u bu adresi tanımalı; yoksa
istekler sessizce düşer:

```sh
cd ../api
DATABASE_URL= CORS_ORIGINS=http://localhost:5000 DEMO_SHOW_OTP_CODE=true \
  python -m uvicorn talimatname.api.app:create_app --factory --port 8010
```

`DATABASE_URL=` boş bırakılınca API **bellek modunda** tohumlu veriyle
kalkar. Telefonda (Android) CORS yok; doğrudan demoya bağlanılır:

```sh
flutter run --dart-define=API_BASE=https://demo.talimatname.com/api/v1
```

SMS sağlayıcısı bağlı olmadığı sürece giriş kodu **ekranda** gösterilir
ve uygulama bunu açıkça söyler (ST-067): "kod telefona gönderilmedi".

## Emülatörde doğrulama (13 Kasım)

Sanal cihaz `talimatname` (Pixel 6, Android 16). Hızlandırma için
Windows Hypervisor Platform açık olmalı.

```sh
emulator -avd talimatname
flutter run --dart-define=API_BASE=https://demo.talimatname.com/api/v1
```

Demo sunucusuna karşı görülenler: giriş, bugünün listeleri, bağlantılı
cevap, **uçak modunda cevap → uygulamayı öldür → aç → kuyruk duruyor →
bağlantı gelince sunucuya ulaşıyor**. Spike A'nın istemci ölçütü buydu.

Görülen ve henüz yapılmayanlar:

- Bağlantı geri geldiğinde senk **kendiliğinden başlamıyor**; yeni bir
  cevap ya da üst banttaki sayaca dokunmak gerekiyor. Arka plan senki
  (WorkManager) sırada.
- Uygulama çevrimdışı açılırsa liste gelmiyor: manifest cihazda
  saklanmıyor. Kuyruk ve oturum duruyor ama ekran boş.
- Listeyi **gönderme** (submit) adımı yok; cevaplar sunucuya gidiyor,
  çalıştırma "devam ediyor"da kalıyor.

## Kapılar

```sh
flutter analyze
flutter test
flutter build apk --debug
```

## Düzen

```
lib/
  api/        sunucuya bakan tek yüz: istemci, modeller, problem+json, oturum deposu
  l10n/       kullanıcıya görünen metinlerin tamamı (ADR-0014 md.7)
  screens/    ekranlar
  state/      Riverpod sağlayıcıları
  theme/      tasarım token'ları ve ThemeData
  widgets/    paylaşılan parçalar
```

**Token'lar panelden türüyor.** Renkler `web/src/styles/tokens.css`
içinde; `test/tokens_match_css_test.dart` CSS'i okuyup buradaki
değerlerle karşılaştırıyor. Panelde bir renk değişirse bu test kırılır
— iki istemcinin zamanla iki ayrı ürüne benzemesini engelleyen şey bu.

**Hata metni `type`'a göre seçilir**, sunucunun Türkçe `title`'ı
ekrana basılmaz (ADR-0014 md.8): `title` değişebilir, `type`
sözleşmedir.

## Web'de kuyruk açılmıyor (12 Kasım)

`web/` altına Drift'in varlıkları kondu (`sqlite3.wasm`, `drift_worker.js`)
ve adresleri `DriftWebOptions` ile verildi, ama tarayıcıda veritabanı
`TypeError: Failed to fetch` ile açılmıyor — üstelik statik sunucunun
günlüğünde **o dosyalara hiç istek görünmüyor**, yani hata getirmeden
önce oluşuyor. Kök nedene inilmedi.

Sonucu: **liste doldurma tarayıcıda denenemiyor**; doğrulama Android
emülatöründe yapılıyor.

Ekran bu durumu saklamıyor: kuyruk açılamazsa üst bantta "Kuyruk
açılamadı" yazıyor. Sessizce "hepsi gönderildi" demek, gönderilmemişken
verilebilecek en pahalı yanlış bilgi olurdu — ilk hâli tam bunu
yapıyordu.

## Bilinen eksikler

- API istemcisi **elle yazıldı**; 02-repo üretilmiş istemci istiyor
  (openapi → dart). Depo arayüzü aynı kaldığı için üretece geçmek
  çağrı yerlerini değiştirmez.
- Metinler tek Dart dosyasında; FR-1803 ARB istiyor.
- **Fotoğraf yok** (Spike C): fotoğraf isteyen madde ekranda
  işaretleniyor, gönderimi sunucu zaten engelliyor.
- Kuyruk yalnızca **cevapları** taşıyor; kanıt kuyruğu fotoğrafla
  birlikte gelecek.
- Gönderilmiş kayıtlar `purgeSent()` ile temizlenebiliyor ama bunu
  çağıran yok: kuyruk tablosu şimdilik büyüyor.
