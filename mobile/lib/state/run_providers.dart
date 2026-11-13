/// Doldurma akışının durumu.
///
/// Ağdan gelen (çalıştırma görünümü, şablon sürümü) ile cihazdan gelen
/// (kuyruk satırları) **ayrı** sağlayıcılar. Sebebi tek cümlede: cevap
/// yazınca ekranın tazelenmesi için ağa gitmek gerekmesin. Şubede
/// bağlantı yok sayılır; yazdığını görmek için ağ beklenmez.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

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
      })
    >((ref) {
      return ({
        required String runId,
        required String itemId,
        required String state,
        Object? value,
      }) async {
        final queue = await ref.read(answerQueueProvider.future);
        await queue.answer(
          runId: runId,
          itemId: itemId,
          state: state,
          value: value,
        );
        ref.invalidate(queuedForRunProvider(runId));
        ref.invalidate(pendingCountProvider);
        // Gönderim beklenmiyor: başarısızsa kayıt kuyrukta kalır ve
        // sayaç bunu gösterir.
        ref.read(syncProvider)().ignore();
      };
    });
