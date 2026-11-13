/// Kuyruğu kendiliğinden gönderir.
///
/// Emülatörde görüldü: bağlantı geri geldiğinde bekleyen cevap, personel
/// sayaca dokunana ya da yeni bir cevap yazana kadar gitmiyordu. Personel
/// bunu bilemez.
///
/// İki tetik var ve ikisi de **uygulama açıkken** çalışır:
///
/// * uygulama öne gelince hemen,
/// * her 20 saniyede bir: bekleyen kayıt varsa gönderir, liste
///   cihazdaki kopyadan geliyorsa yeniden ister.
///
/// Uygulama arka plandayken gönderim ayrı: `background/sync_worker.dart`
/// (WorkManager). Bu sınıf yalnızca işi oraya devredip geri alıyor.
/// Bağlantı dinleyicisi yerine süreli deneme seçildi: "bağlantı var"
/// sinyali sunucuya ulaşılabildiğini göstermez (şube Wi-Fi'ı açık ama
/// internet yok), denemek gösterir.
library;

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../background/sync_worker.dart';
import '../state/providers.dart';

const autoSyncInterval = Duration(seconds: 20);

class AutoSync extends ConsumerStatefulWidget {
  const AutoSync({required this.child, super.key});

  final Widget child;

  @override
  ConsumerState<AutoSync> createState() => _AutoSyncState();
}

class _AutoSyncState extends ConsumerState<AutoSync>
    with WidgetsBindingObserver {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _timer = Timer.periodic(autoSyncInterval, (_) => _tick());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _onResume();
    } else if (state == AppLifecycleState.paused) {
      _onPause();
    }
  }

  /// Öne gelince: arka plan işini durdur, onun döndürmüş olabileceği
  /// oturumu yeniden oku, sonra kendi senkini yap. Sıra önemli.
  Future<void> _onResume() async {
    await cancelBackgroundSync();
    if (!mounted) return;
    await ref.read(sessionProvider.notifier).reload();
    ref.invalidate(pendingCountProvider);
    ref.read(syncTickProvider.notifier).bump();
    await _tick();
  }

  /// Arka plana geçerken bekleyen kayıt varsa işi Android'e bırak.
  Future<void> _onPause() async {
    if (ref.read(sessionProvider).value == null) return;
    final bekleyen = await ref.read(pendingCountProvider.future);
    if (bekleyen > 0) await scheduleBackgroundSync();
  }

  Future<void> _tick() async {
    if (ref.read(sessionProvider).value == null) return;
    // Liste cihazdaki kopyadan geliyorsa yeniden iste: bağlantı
    // döndüyse uyarı kalkar, dönmediyse aynı kopya kalır.
    if (ref.read(manifestDocProvider).value?.stale ?? false) {
      ref.invalidate(manifestDocProvider);
      ref.read(refetchTickProvider.notifier).bump();
    }
    final bekleyen = await ref.read(pendingCountProvider.future);
    if (bekleyen == 0) return;
    await ref.read(syncProvider)();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
