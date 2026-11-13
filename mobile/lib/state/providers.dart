/// Riverpod sağlayıcıları: istemci, oturum ve manifest.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../api/run_models.dart';
import '../api/session_store.dart';
import '../queue/answer_queue.dart';
import '../queue/database.dart';

final sessionStoreProvider = Provider<SessionStore>((ref) => SessionStore());

final apiClientProvider = Provider<ApiClient>((ref) {
  final store = ref.watch(sessionStoreProvider);
  final client = ApiClient(
    onSessionChanged: (session) {
      // Yenileme belirteci her yenilemede **döndüğü** için saklanan
      // değer hemen güncellenmeli: eski belirteç iptal olur ve ikinci
      // kez kullanılırsa zincirin tamamı düşer.
      if (session == null) {
        store.clear();
        // Oturum düştüyse ekran da düşmeli: yoksa her sağlayıcı
        // yenilemeyi kendi başına yeniden dener.
        ref.read(sessionProvider.notifier).dropped();
      } else {
        store.write(session);
      }
    },
  );
  ref.onDispose(client.close);
  return client;
});

/// Açılışta saklanan oturumu yükler; yoksa `null`.
class SessionController extends AsyncNotifier<Session?> {
  @override
  Future<Session?> build() async {
    final store = ref.read(sessionStoreProvider);
    final client = ref.read(apiClientProvider);
    final stored = await store.read();
    if (stored == null) return null;
    if (!stored.refreshUsable) {
      await store.clear();
      return null;
    }
    client.adopt(stored);
    return stored;
  }

  Future<String?> requestCode(String phone) =>
      ref.read(apiClientProvider).requestCode(phone);

  Future<void> verify(String phone, String code) async {
    final session = await ref.read(apiClientProvider).verify(phone, code);
    state = AsyncData(session);
  }

  Future<void> signOut() async {
    await ref.read(apiClientProvider).signOut();
    state = const AsyncData(null);
  }

  /// Sunucu oturumu kabul etmedi; kullanıcı giriş ekranına döner.
  void dropped() {
    if (state.value != null) state = const AsyncData(null);
  }
}

final sessionProvider = AsyncNotifierProvider<SessionController, Session?>(
  SessionController.new,
);

/// Bugünün listeleri. Oturum değişince kendiliğinden yeniden çekilir.
final manifestProvider = FutureProvider<Manifest>((ref) async {
  final session = await ref.watch(sessionProvider.future);
  if (session == null) {
    throw StateError('oturum yok');
  }
  return ref.read(apiClientProvider).manifest();
});

/// Kuyruk veritabanı. Uygulama ömrü boyunca tek örnek.
final queueDatabaseProvider = Provider<QueueDatabase>((ref) {
  final db = QueueDatabase();
  ref.onDispose(db.close);
  return db;
});

/// Cihaz kimliği: kayıtla birlikte gidiyor ki aynı çalıştırmayı iki
/// cihaz doldurduğunda hangisinin yazdığı belli olsun. Oturumdan
/// bağımsız, cihaza ait ve kalıcı.
final deviceIdProvider = FutureProvider<String>((ref) async {
  final store = ref.read(sessionStoreProvider);
  final mevcut = await store.readDeviceId();
  if (mevcut != null) return mevcut;
  final yeni = newAnswerId();
  await store.writeDeviceId(yeni);
  return yeni;
});

final answerQueueProvider = FutureProvider<AnswerQueue>((ref) async {
  return AnswerQueue(
    db: ref.read(queueDatabaseProvider),
    api: ref.read(apiClientProvider),
    deviceId: await ref.watch(deviceIdProvider.future),
  );
});

final pendingCountProvider = FutureProvider<int>((ref) async {
  final queue = await ref.watch(answerQueueProvider.future);
  return queue.pendingCount();
});

/// Senk sürüyor mu — düğmeyi iki kez bastırmamak için.
class SyncingNotifier extends Notifier<bool> {
  @override
  bool build() => false;

  void set(bool value) => state = value;
}

final syncingProvider = NotifierProvider<SyncingNotifier, bool>(
  SyncingNotifier.new,
);

/// Her senk turundan sonra artan sayaç. Kuyruk satırlarını gösteren
/// sağlayıcılar bunu izliyor: gönderim satırların `sent` durumunu
/// değiştiriyor ama ekran bunu kendiliğinden öğrenemiyor. İlk hâlinde
/// gönderilmiş cevap "Gönderilmeyi bekliyor" diye kalıyordu, üst bant
/// ise "Hepsi gönderildi" diyordu — emülatörde görüldü.
class SyncTick extends Notifier<int> {
  @override
  int build() => 0;

  void bump() => state++;
}

final syncTickProvider = NotifierProvider<SyncTick, int>(SyncTick.new);

/// Kuyruğu gönderir. Sonuç ekranda sayacı tazeler; hata **yutulmaz**,
/// kayıt kuyrukta kalır ve sayaç bunu gösterir.
final syncProvider = Provider<Future<SyncOutcome> Function()>((ref) {
  return () async {
    if (ref.read(syncingProvider)) {
      return const SyncOutcome();
    }
    ref.read(syncingProvider.notifier).set(true);
    try {
      final queue = await ref.read(answerQueueProvider.future);
      final policy = ref.read(manifestProvider).value?.policy;
      return await queue.sync(policy: policy);
    } finally {
      ref.read(syncingProvider.notifier).set(false);
      ref.invalidate(pendingCountProvider);
      ref.read(syncTickProvider.notifier).bump();
    }
  };
});
