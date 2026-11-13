/// Yakındaki listelerin içeriğini önden indirir.
///
/// Manifest listeyi taşıyor ama **maddeleri taşımıyor** (Spike A
/// bulgusu): çalıştırma görünümü ve şablon sürümü ayrı isteklerle
/// geliyor. Önden indirilmezse, vardiya başında bağlantı varken listeyi
/// açmamış personel bağlantı gidince o listeyi dolduramaz — sahada en
/// sık karşılaşılacak durum.
///
/// Hepsi değil, **yakındakiler** indiriliyor: şu an yazılabilir olanlar
/// ve [prefetchWindow] içinde açılacaklar. Manifestin ufku 48 saat;
/// yarının listelerini bugün indirmek hem mobil veriyi harcar hem de
/// yarına kadar bayatlar.
library;

import '../api/models.dart';
import '../api/problem.dart';
import 'doc_cache.dart';

const prefetchWindow = Duration(hours: 12);

/// Çalıştırma görünümü bu süreden yeniyse yeniden indirilmez: manifest
/// her tazelendiğinde bütün listeleri yeniden çekmemek için.
const runViewFreshness = Duration(minutes: 15);

/// Önden indirilecek çalıştırmalar: penceresi kapanmamış ve en geç
/// [prefetchWindow] içinde yazmaya açılacak olanlar.
List<ManifestRun> prefetchTargets(Manifest manifest, DateTime now) => [
  for (final run in manifest.runs)
    if (now.isBefore(run.toleranceEnd) &&
        !run.writableFrom.isAfter(now.add(prefetchWindow)))
      run,
];

/// Hedeflerin görünümünü ve şablon sürümünü önbelleğe alır; kaç belgenin
/// indirildiğini döndürür.
///
/// Ağ hatasında **sessizce durur**: önden indirme bir iyileştirmedir,
/// başarısızlığı kullanıcıya hata olarak gösterilmez. Liste açılırken
/// gereken belge yoksa hata orada, bağlamıyla görünür.
Future<int> prefetchRuns(
  DocCache cache,
  Manifest manifest,
  DateTime now,
) async {
  var indirilen = 0;
  final surumler = <String>{};
  try {
    for (final run in prefetchTargets(manifest, now)) {
      if (await cache.warm('/runs/${run.runId}', maxAge: runViewFreshness)) {
        indirilen++;
      }
      // Yayınlanmış sürüm değişmez (BR-18): bir kez inmişse yeter.
      if (surumler.add(run.templateVersionId) &&
          await cache.warm('/template-versions/${run.templateVersionId}')) {
        indirilen++;
      }
    }
  } on ApiException {
    // Bağlantı gitti ya da sunucu reddetti; indirilenler duruyor.
  }
  return indirilen;
}
