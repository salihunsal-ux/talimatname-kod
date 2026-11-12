/// Kullanıcıya görünen metinler — **tek yerde** (ADR-0014 md.7).
///
/// FR-1803 i18n kaynak dosyası istiyor (ARB). Şimdilik tek dil ve tek
/// dosya: ARB'ye geçince bu sınıf üretilen `AppLocalizations` ile
/// değişir, çağrı yerleri değişmez. Makine metni (hata `type`'ı, URN,
/// kod) ekranda görünmez (05-tasarim/04).
///
/// Etiketler **panelin** `web/src/i18n/tr.ts` karşılıklarıyla birebir:
/// aynı duruma iki istemcide iki ad vermek, kullanıcıya iki ürün
/// gösterir. Panelde bir etiket değişirse buraya da taşınmalı.
library;

abstract final class S {
  static const appTitle = 'Talimatname';
  static const tagline = 'Kanıtlı görev listesi';

  // Giriş
  static const signInTitle = 'Giriş';
  static const signInHint = 'Telefonunuza gelen kodla girin';
  static const phoneLabel = 'Telefon numarası';
  static const phoneExample = '0532 000 00 00';
  static const requestCode = 'Kod iste';
  static const codeLabel = 'Doğrulama kodu';
  static const signIn = 'Giriş yap';
  static const changePhone = 'Numarayı değiştir';

  /// SMS sağlayıcısı bağlı olmadığı sürece kod **gönderilmiyor**;
  /// ekranda gösteriliyor (ST-067). Panelle aynı metin.
  static const smsNotConnected =
      'SMS sağlayıcısı henüz bağlı değil: kod telefona gönderilmedi.';
  static String codeOnScreen(String code) => 'Giriş kodu: $code';
  static const signOut = 'Çıkış';
  static const sessionEnded = 'Oturumunuz sona erdi, yeniden girin';

  // Bugün
  static const todayTitle = 'Bugünün listeleri';
  static const refresh = 'Yenile';
  static const todayEmpty = 'Bugün için çalıştırma yok.';
  static const todayEmptyHint =
      'Plan penceresi açılınca listeler burada görünür.';
  static const openNow = 'Şimdi açık';
  static const notYetOpen = 'Henüz açılmadı';
  static const windowClosed = 'Pencere kapandı';
  static String windowRange(String start, String end) => '$start–$end';
  static const today = 'Bugün';
  static const tomorrow = 'Yarın';

  /// Ay adları; `intl` paketi gelene kadar tek yerde.
  static const months = <String>[
    'Ocak',
    'Şubat',
    'Mart',
    'Nisan',
    'Mayıs',
    'Haziran',
    'Temmuz',
    'Ağustos',
    'Eylül',
    'Ekim',
    'Kasım',
    'Aralık',
  ];

  /// Çalıştırma durumları — panelin `durumlar` haritası.
  static const status = <String, String>{
    'scheduled': 'Planlı',
    'in_progress': 'Devam ediyor',
    'submitted': 'Tamamlandı',
    'missed': 'Kaçırıldı',
    'cancelled': 'Yapılmayacak',
  };

  // Hata
  static const genericError = 'Bir şey ters gitti. Tekrar deneyin.';
  static const networkError =
      'Sunucuya ulaşılamadı. Bağlantınızı kontrol edin.';
  static const retry = 'Tekrar dene';
}
