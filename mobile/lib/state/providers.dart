/// Riverpod sağlayıcıları: istemci, oturum ve manifest.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../api/session_store.dart';

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
