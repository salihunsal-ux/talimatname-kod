# Saha istemcisi (Flutter)

Personelin listeyi doldurduğu uygulama. Panel (`web/`) yöneticiler
için; burası şubede, telefonda, çoğu zaman **zayıf bağlantıyla**
çalışır.

Bu sürüm **ilk dikey dilim**: giriş → bugünün listeleri. Madde
doldurma, kanıt çekme ve çevrimdışı kuyruk henüz yok.

## Hedefler

| Hedef | Durum | Not |
|---|---|---|
| Android | **asıl hedef** | `flutter build apk` |
| Web | yalnızca geliştirme | Hızlı arayüz döngüsü. Dağıtılmaz: tarayıcıda güvenli depo yok, belirteç localStorage'a düşer |
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

## Bilinen eksikler

- API istemcisi **elle yazıldı**; 02-repo üretilmiş istemci istiyor
  (openapi → dart). Depo arayüzü aynı kaldığı için üretece geçmek
  çağrı yerlerini değiştirmez.
- Metinler tek Dart dosyasında; FR-1803 ARB istiyor.
- Çevrimdışı kuyruk (Drift) yok. Sunucu sözleşmesi Spike A'da
  doğrulandı (`api/tests/test_spike_a_senk.py`), istemci tarafı sırada.
