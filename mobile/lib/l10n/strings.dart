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

  // Liste doldurma
  static const answerYes = 'Evet';
  static const answerNo = 'Hayır';
  static const answerNotDone = 'Yapılamadı';
  static const criticalItem = 'Kritik';
  static const valueLabel = 'Değer';
  static const noOptions = 'Bu madde için seçenek tanımlı değil.';
  static const reasonTitle = 'Neden yapılamadı?';
  static const takePhoto = 'Fotoğraf çek';
  static String photoCount(int n, int sinir) => '$n/$sinir fotoğraf';
  static const photoRequiredHint = 'Bu madde fotoğraf istiyor.';
  static const photoIssueHint = 'Olumsuz cevap fotoğraf da ister.';
  static const photoPending = 'Fotoğraf yüklenmeyi bekliyor';
  static const photoRejected = 'Bir fotoğrafı sunucu kabul etmedi';
  static const photoNeedsAnswer = 'Önce maddeyi cevaplayın.';
  static const photoItemFull = 'Bu madde için fotoğraf sınırı doldu.';
  static const photoQueueFull =
      'Cihazda bekleyen fotoğraf sınırı doldu. Bağlantı gelip yüklenince '
      'yenisini çekebilirsiniz.';
  static const photoUnsupported = 'Bu cihazda fotoğraf çekilemiyor.';
  static const locationWhyTitle = 'Konum neden isteniyor?';
  static const locationWhyBody =
      'Fotoğrafın şubede çekildiğini göstermek için çekim anındaki konum '
      'fotoğrafla birlikte kaydedilir. Konum yalnızca fotoğraf çekerken '
      'okunur; sürekli izlenmez. İzin vermezseniz de fotoğraf çekebilirsiniz, '
      'o fotoğraf “konum yok” olarak işaretlenir.';
  static const locationWhyOk = 'Anladım';
  static const cameraMissing = 'Bu cihazda kamera bulunamadı.';
  static const cameraDenied =
      'Kamera izni verilmedi. Ayarlardan izin verip yeniden deneyin.';
  static const cameraFailed = 'Fotoğraf çekilemedi. Yeniden deneyin.';
  static const cameraClose = 'Kapat';
  static const cameraUse = 'Kullan';
  static const cameraRetake = 'Yeniden çek';
  static const cameraReviewHint =
      'Gönderilen fotoğraf silinemez. Uygunsa kullanın.';
  static const photoRemove = 'Fotoğrafı kaldır';
  static const photoOnServer = 'Gönderildi';
  static const cameraShoot = 'Fotoğraf çek';
  static const noteLabel = 'Not (zorunlu)';
  static const submit = 'Listeyi gönder';
  static const submitting = 'Gönderiliyor…';
  static const submitNeedsNetwork =
      'Göndermek için bağlantı gerekli. Cevaplarınız cihazda duruyor.';
  static const submitBlocked = 'Liste gönderilemedi. Eksikler:';
  static const blockerKinds = <String, String>{
    'unanswered': 'cevaplanmadı',
    'evidence': 'fotoğraf eksik',
    'note': 'not eksik',
  };
  static const submitted = 'Liste gönderildi';
  static String score(int puan) => 'Puan: %$puan';
  static const resultLabels = <String, String>{
    'passed': 'Başarılı',
    'failed': 'Başarısız',
  };
  static String offlineSince(String saat) =>
      'Çevrimdışı: liste $saat itibarıyla. Cevaplarınız cihazda saklanır.';
  static const alreadySubmitted = 'Bu liste gönderildi; artık değiştirilemez.';
  static const readOnlyWindow = 'Pencere kapalı: bu listeye artık yazılamaz.';
  static String lockedBy(String ad) => '$ad bu listeyi üstlendi.';
  static const pendingOne = 'Gönderilmeyi bekliyor';
  static const rejectedOne = 'Sunucu bu cevabı kabul etmedi';
  static const allSent = 'Hepsi gönderildi';
  static const queueBroken = 'Kuyruk açılamadı';
  static String pending(int n) => '$n bekliyor';
  static String range(num? alt, num? ust, String? birim) {
    final ek = birim == null ? '' : ' $birim';
    if (alt != null && ust != null) return 'Beklenen: $alt – $ust$ek';
    if (alt != null) return 'En az $alt$ek';
    return 'En çok $ust$ek';
  }
}
