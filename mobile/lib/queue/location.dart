/// Fotoğraf çekilirken cihazın konumu.
///
/// Konum **yalnızca çekim anında** okunur ve kanıtla birlikte gider:
/// fotoğrafın şubede çekildiğini göstermek için (sunucu konumsuz kanıtı
/// "konum yok" bayrağıyla işaretliyor). Sürekli izleme, arka plan konumu
/// ya da konum geçmişi yok; izin de "uygulama kullanılırken" izni.
///
/// Konum alınamaması fotoğrafı **engellemez**: izin verilmediyse, GPS
/// kapalıysa ya da süre dolduysa kare konumsuz gider ve bayrağı sunucu
/// koyar. Personeli konum yüzünden işini yapamaz bırakmak, bayraktan
/// daha pahalı.
library;

import 'package:geolocator/geolocator.dart';

/// Konum için beklenecek en uzun süre. Fotoğrafın kabulünü geciktirir;
/// kapalı mekânda GPS uzun sürebilir, o yüzden kısa tutuluyor ve son
/// bilinen konuma düşülüyor.
const locationTimeout = Duration(seconds: 4);

typedef Coordinates = ({double latitude, double longitude});

/// İzin durumu: sistem penceresinden önce açıklama gösterilmeli mi.
Future<bool> locationNeedsRationale() async {
  try {
    return await Geolocator.checkPermission() == LocationPermission.denied;
  } on Object {
    return false;
  }
}

/// Geçerli konum; alınamazsa `null`.
Future<Coordinates?> currentCoordinates() async {
  try {
    if (!await Geolocator.isLocationServiceEnabled()) return null;
    var izin = await Geolocator.checkPermission();
    if (izin == LocationPermission.denied) {
      izin = await Geolocator.requestPermission();
    }
    if (izin == LocationPermission.denied ||
        izin == LocationPermission.deniedForever) {
      return null;
    }
    Position? konum;
    try {
      konum = await Geolocator.getCurrentPosition(
        // Android'in kendi konum yöneticisi, Google Play servisleri
        // değil. Play servisleri yolu emülatörde "Konum Doğruluğu"
        // penceresini açtı: personelden ayrıca Google'a veri paylaşımı
        // onayı istemek demek. Kanıt için şube düzeyinde doğruluk
        // yeter; o onaya değmez.
        locationSettings: AndroidSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: locationTimeout,
          forceLocationManager: true,
        ),
      );
    } on Object {
      // Süre doldu ya da sinyal yok: son bilinen konum, hiç yoktan iyi.
      konum = await Geolocator.getLastKnownPosition(
        forceAndroidLocationManager: true,
      );
    }
    if (konum == null) return null;
    return (latitude: konum.latitude, longitude: konum.longitude);
  } on Object {
    return null;
  }
}
