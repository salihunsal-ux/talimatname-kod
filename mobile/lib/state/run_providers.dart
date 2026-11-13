/// Doldurma akışının durumu.
///
/// Ağdan gelen (çalıştırma görünümü, şablon sürümü) ile cihazdan gelen
/// (kuyruk satırları) **ayrı** sağlayıcılar. Sebebi tek cümlede: cevap
/// yazınca ekranın tazelenmesi için ağa gitmek gerekmesin. Şubede
/// bağlantı yok sayılır; yazdığını görmek için ağ beklenmez.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/problem.dart';
import '../api/run_models.dart';
import '../queue/database.dart';
import 'providers.dart';

/// Ağdan gelen kısım: görünüm + seçenekler.
class RunDetail {
  const RunDetail({required this.view, required this.options});

  final RunView view;
  final Map<String, VersionItem> options;
}

final runDetailProvider = FutureProvider.family<RunDetail, String>((
  ref,
  runId,
) async {
  final api = ref.read(apiClientProvider);
  final view = await api.run(runId);
  final versionId = await ref.watch(runVersionProvider(runId).future);
  return RunDetail(
    view: view,
    options: versionId == null
        ? const {}
        : await ref.watch(templateVersionProvider(versionId).future),
  );
});

/// Cihazdaki kuyruk satırları. Cevap yazınca **yalnızca bu** tazelenir.
final queuedForRunProvider = FutureProvider.family<List<QueuedAnswer>, String>((
  ref,
  runId,
) async {
  // Senk satırların durumunu değiştirir; tur bitince yeniden oku.
  ref.watch(syncTickProvider);
  final queue = await ref.watch(answerQueueProvider.future);
  return queue.forRun(runId);
});

/// Çalıştırmanın şablon sürümü manifestten okunuyor: görünüm onu
/// taşımıyor (Spike A bulgusu).
final runVersionProvider = FutureProvider.family<String?, String>((
  ref,
  runId,
) async {
  final manifest = await ref.watch(manifestProvider.future);
  for (final run in manifest.runs) {
    if (run.runId == runId) return run.templateVersionId;
  }
  return null;
});

/// Yayınlanmış sürüm değişmez (BR-18): bir kez indirilir ve saklanır.
final templateVersionProvider =
    FutureProvider.family<Map<String, VersionItem>, String>((
      ref,
      versionId,
    ) async {
      ref.keepAlive();
      return ref.read(apiClientProvider).templateVersion(versionId);
    });

/// Cevabı kuyruğa yazar; ekranı ağa gitmeden tazeler ve bağlantı varsa
/// arka planda gönderir.
final answerProvider =
    Provider<
      Future<void> Function({
        required String runId,
        required String itemId,
        required String state,
        Object? value,
        String? note,
        String? notDoneReason,
      })
    >((ref) {
      return ({
        required String runId,
        required String itemId,
        required String state,
        Object? value,
        String? note,
        String? notDoneReason,
      }) async {
        final queue = await ref.read(answerQueueProvider.future);
        await queue.answer(
          runId: runId,
          itemId: itemId,
          state: state,
          value: value,
          note: note,
          notDoneReason: notDoneReason,
        );
        ref.invalidate(queuedForRunProvider(runId));
        ref.invalidate(pendingCountProvider);
        // Gönderim beklenmiyor: başarısızsa kayıt kuyrukta kalır ve
        // sayaç bunu gösterir.
        ref.read(syncProvider)().ignore();
      };
    });

/// Gönderme denemesinin sonucu.
sealed class SubmitOutcome {
  const SubmitOutcome();
}

/// Gönderildi; sonuç ve puan görünümde.
class SubmitDone extends SubmitOutcome {
  const SubmitDone(this.view);

  final RunView view;
}

/// Sunucuya ulaşılamadı ya da kuyruk boşaltılamadı. Cevaplar cihazda.
class SubmitNeedsNetwork extends SubmitOutcome {
  const SubmitNeedsNetwork();
}

/// Sunucu eksik buldu; liste **sunucunun** verdiği eksikler.
class SubmitBlocked extends SubmitOutcome {
  const SubmitBlocked(this.blockers);

  final List<Blocker> blockers;
}

/// Sunucu başka bir sebeple reddetti (pencere kapandı, kilit başkasında).
class SubmitRejected extends SubmitOutcome {
  const SubmitRejected(this.error);

  final ApiException error;
}

/// Listeyi gönderir: önce kuyruğu boşaltır, sonra sunucudan ister.
///
/// Sıra önemli: kuyrukta bekleyen cevap varken göndermek, sunucunun
/// görmediği cevaplarla puan hesaplatmak olurdu. Eksikleri cihaz
/// **hesaplamıyor**; sunucunun listesini gösteriyor — kural iki yerde
/// yaşarsa iki kural olur.
final submitProvider = Provider<Future<SubmitOutcome> Function(String runId)>((
  ref,
) {
  return (runId) async {
    final senk = await ref.read(syncProvider)();
    if (!senk.ok || senk.remaining > 0) {
      // Kalıcı ret alan kayıt `remaining`e girmiyor; o durumda sunucu
      // eksik olarak söyleyecek.
      return const SubmitNeedsNetwork();
    }
    final api = ref.read(apiClientProvider);
    try {
      final view = await api.submit(runId);
      ref.invalidate(runDetailProvider(runId));
      ref.invalidate(manifestProvider);
      return SubmitDone(view);
    } on ApiException catch (hata) {
      if (hata.isNetwork) return const SubmitNeedsNetwork();
      if (hata.statusCode == 422) {
        try {
          final view = await api.run(runId);
          ref.invalidate(runDetailProvider(runId));
          if (view.blockers.isNotEmpty) return SubmitBlocked(view.blockers);
        } on ApiException {
          // Eksik listesi alınamadı; genel ret olarak göster.
        }
      }
      return SubmitRejected(hata);
    }
  };
});
