# Saha istemcisi (Flutter)

Personelin listeyi doldurduğu uygulama. Panel (`web/`) yöneticiler
için; burası şubede, telefonda, çoğu zaman **zayıf bağlantıyla**
çalışır.

Bugünkü hâli: giriş → bugünün listeleri → liste doldurma, kanıt
fotoğrafı, çevrimdışı kuyruk ve gönderme. Yalnızca emülatörde görüldü.

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

Sonradan eklenen ve aynı yolla görülenler (yerel API'ye karşı,
`--dart-define=API_BASE=http://10.0.2.2:8010/api/v1`):

- **Listeyi gönderme:** eksik varken sunucunun eksik listesi, tamamken
  "Liste gönderildi · Başarılı · Puan: %100".
- **"Yapılamadı" sebebi ve not:** sebep seçilmeden cevap yazılmıyor,
  olumsuz cevapta not alanı açılıyor (BR-06, BR-09).
- **Çevrimdışı açılış:** liste ve çalıştırma cihazdaki son kopyadan
  geliyor, "Çevrimdışı: liste SS:DD itibarıyla" uyarısıyla. Yalnızca ağ
  hatasında kopyaya düşülür; sunucu "hayır" dediyse eski kopya
  gösterilmez.
- **Otomatik senk:** uygulama açıkken her 20 saniyede bir ve öne
  gelince. Bağlantı dönünce bekleyen cevap dokunmadan gidiyor, uyarı
  kendiliğinden kalkıyor.

- **Fotoğraf (Spike C, emülatörde):** madde cevaplanınca "Fotoğraf çek"
  düğmesi çıkıyor; uygulama içi kamera, deklanşör, cihazda sıkıştırma
  (hedef ≤ 300 KB) ve SHA-256. Fotoğraf cevaptan **sonra** gönderiliyor,
  baytlar yüklenip sunucuda özetle doğrulanıyor ("stored"). Galeri yolu
  yok. Damgayı sunucu basıyor.

- **Önden indirme:** manifest taze gelince, şu an açık olan ve 12 saat
  içinde açılacak listelerin maddeleri arka planda iniyor. Hiç
  açılmamış liste çevrimdışı açılabiliyor (emülatörde: giriş, listeyi
  açmadan uçak modu, öldür-aç, liste maddeleriyle açıldı). 12 saatten
  uzaktaki listeler inmiyor.

- **Fotoğrafı görme ve kaldırma:** maddede küçük resim şeridi, dokununca
  büyütme. Cihazdan çıkmamış kare kaldırılabilir; **yüklenmiş kanıt
  kaldırılamaz** — sunucuda silme ucu yok ve bu bilinçli (FR-0609,
  "kanıt silinmez"). Yanlış karenin kayda girmemesi için çekimden sonra
  önizleme var ("Yeniden çek / Kullan"). Bu, Spike C'nin "2 dokunuş"
  hedefini **üçe** çıkarıyor; karar bilinçli ve geri alınabilir.
  Yüklenmiş kare cihazdan silindiği için yalnızca bağlantı varken
  görünür.

- **Konum (BR-15):** fotoğraf çekilirken okunuyor ve kanıtla gidiyor;
  sunucu konumlu kanıta "konum yok" bayrağı koymuyor. İzin "uygulama
  kullanılırken"; önce açıklama gösteriliyor. Android'in kendi konum
  yöneticisi kullanılıyor (Play servisleri yolu Google'a veri paylaşımı
  onayı istiyordu). Konum alınamazsa fotoğraf yine çekilir.
  Emülatörde sahte GPS konumuyla görüldü.

- **Arka plan senki (WorkManager):** uygulama arka plana geçerken
  bekleyen kayıt varsa ağ koşullu bir iş kuyruğa alınıyor; bağlantı
  gelince Android onu kendisi çalıştırıyor. Emülatörde görüldü:
  çevrimdışı cevap, ana ekrana çıkış, bağlantı açıldı, iş 2 saniye
  içinde çalıştı ve cevap uygulama açılmadan sunucuya ulaştı.
  Uygulama öne gelince iş iptal ediliyor ve saklanan oturum yeniden
  okunuyor: arka planda dönen yenileme belirteci bellekteki eskisiyle
  kullanılırsa sunucu zinciri iptal eder.

Hâlâ yapılmayanlar:

- **Arka plan senkinin sınırları ölçülmedi.** Android, pil tasarrufu ve
  üretici kısıtlarıyla (Xiaomi, Huawei, Samsung) arka plan işlerini
  geciktirebilir ya da hiç çalıştırmayabilir; emülatörde bunların hiçbiri
  yok. Uygulama zorla durdurulursa (ayarlardan "Durdur") iş de silinir.
  Kayıt kaybolmaz, uygulama açılınca gider.
- **Gerçek cihaz ölçümü yok.** Emülatörün kamerası sahte sahne veriyor:
  kare 14 KB'a sıkıştı ve kameranın ilk açılışı ~10 sn sürdü. İkisi de
  gerçek telefonu temsil etmiyor. Spike C'nin kabul ölçütleri (çekim →
  madde tamam ≤ 3 sn, dosya ≤ 300 KB ve **okunur**) düşük segment bir
  Android'de ölçülmeden kapanmış sayılmaz.

Derleme notu: `android/gradle.properties` içinde `kotlin.incremental=false`.
Proje ile pub önbelleği farklı sürücülerdeyse (D: ve C:) Kotlin derleyen
eklentiler "Could not close incremental caches" ile kırılıyor.

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
