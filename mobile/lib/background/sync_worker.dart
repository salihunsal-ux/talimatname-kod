/// Uygulama kapalıyken kuyruğu gönderen arka plan işi (WorkManager).
///
/// Senaryo: personel bağlantısız doldurdu, telefonu cebine koydu.
/// Uygulama içi otomatik senk yalnızca uygulama açıkken çalışıyor; o
/// yüzden cevaplar personel uygulamayı yeniden açana kadar cihazda
/// kalıyordu. Bu iş, uygulama arka plana geçerken **ağ koşuluyla**
/// kuyruğa alınıyor: bağlantı geldiğinde Android onu kendisi çalıştırır.
///
/// Ayrı bir isolate'te koşar; uygulamanın sağlayıcılarına erişemez.
/// Oturumu, kuyruğu ve istemciyi kendi kurar.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:ui';

import 'package:flutter/widgets.dart';
import 'package:path_provider/path_provider.dart';
import 'package:workmanager/workmanager.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../api/session_store.dart';
import '../queue/answer_queue.dart';
import '../queue/database.dart';

const backgroundSyncTask = 'kuyruk-senk';
const backgroundSyncUniqueName = 'talimatname.kuyruk-senk';

@pragma('vm:entry-point')
void backgroundDispatcher() {
  Workmanager().executeTask((task, input) async {
    WidgetsFlutterBinding.ensureInitialized();
    DartPluginRegistrant.ensureInitialized();
    try {
      return await runBackgroundSync();
    } on Object catch (hata) {
      // Beklenmeyen hata: yeniden denensin. Kayıtlar kuyrukta duruyor.
      _log('hata: ${hata.runtimeType}');
      return false;
    }
  });
}

/// Arka plan işinin günlüğü. Yalnızca **hangi adımda** ne olduğu
/// yazılır; kişi, cevap ya da belirteç yazılmaz. İş ekransız koştuğu
/// için sessizce "başarılı" dönmesi tanılanamıyordu: emülatörde iş
/// çalıştı, başarılı döndü ve hiçbir şey göndermedi.
void _log(String mesaj) {
  // ignore: avoid_print
  print('[arka-plan-senk] $mesaj');
}

/// Kuyruğu boşaltmayı dener. `true`: iş bitti (yeniden deneme gereksiz);
/// `false`: ağ yüzünden bitmedi, Android geri çekilerek yeniden dener.
Future<bool> drainQueue(AnswerQueue queue, {QueuePolicy? policy}) async {
  if (await queue.pendingCount() == 0) return true;
  final sonuc = await queue.sync(policy: policy);
  // Yalnızca ağ hatası yeniden denemeye değer. Oturum düştüyse ya da
  // sunucu reddettiyse tekrar denemek aynı cevabı alır; kayıt kuyrukta
  // kalır ve kullanıcı uygulamayı açınca görür.
  return !(sonuc.failure?.isNetwork ?? false);
}

Future<bool> runBackgroundSync() async {
  final store = SessionStore();
  final session = await store.read();
  if (session == null || !session.refreshUsable) {
    _log('oturum yok');
    return true;
  }
  final deviceId = await store.readDeviceId();
  if (deviceId == null) {
    _log('cihaz kimliği yok');
    return true;
  }

  // Yenileme belirteci her yenilemede **dönüyor**. Arka planda dönen
  // belirteç saklanmazsa, uygulama açıldığında eskisini kullanır ve
  // sunucu bunu çalınmış belirteç sayıp zincirin tamamını iptal eder.
  // Yazma bu yüzden işin sonunda **beklenerek** yapılıyor; geri çağrı
  // içinde beklenmeyen bir yazma, süreç ölünce kaybolabilir.
  Session? sonOturum;
  var oturumDustu = false;
  final api = ApiClient(
    onSessionChanged: (s) {
      sonOturum = s;
      oturumDustu = s == null;
    },
  )..adopt(session);

  final db = QueueDatabase();
  try {
    final kok = await getApplicationDocumentsDirectory();
    final queue = AnswerQueue(
      db: db,
      api: api,
      deviceId: deviceId,
      evidenceDir: Directory('${kok.path}${Platform.pathSeparator}kanit'),
    );
    final bekleyen = await queue.pendingCount();
    final bitti = await drainQueue(queue, policy: await _cachedPolicy(db));
    _log(
      'bekleyen $bekleyen → kalan ${await queue.pendingCount()}, '
      '${bitti ? 'bitti' : 'yeniden denenecek'}',
    );
    return bitti;
  } finally {
    if (oturumDustu) {
      await store.clear();
    } else if (sonOturum != null) {
      await store.write(sonOturum!);
    }
    api.close();
    await db.close();
  }
}

/// Parti sınırları cihazdaki son manifestten; yoksa sözleşme varsayılanı.
Future<QueuePolicy?> _cachedPolicy(QueueDatabase db) async {
  try {
    final kayit = await db.getDoc('/sync/manifest');
    if (kayit == null) return null;
    final json = jsonDecode(kayit.body) as Map<String, dynamic>;
    return QueuePolicy.fromJson(json['policy'] as Map<String, dynamic>);
  } on Object {
    return null;
  }
}

bool get _supported => Platform.isAndroid;

/// Uygulama açılışında bir kez.
Future<void> initBackgroundSync() async {
  if (!_supported) return;
  await Workmanager().initialize(backgroundDispatcher);
}

/// Uygulama arka plana geçerken, bekleyen kayıt varsa. Ağ koşulu
/// Android'e bırakılıyor: bağlantı gelince iş kendiliğinden başlar.
Future<void> scheduleBackgroundSync() async {
  if (!_supported) return;
  await Workmanager().registerOneOffTask(
    backgroundSyncUniqueName,
    backgroundSyncTask,
    constraints: Constraints(networkType: NetworkType.connected),
    existingWorkPolicy: ExistingWorkPolicy.replace,
    backoffPolicy: BackoffPolicy.exponential,
    backoffPolicyDelay: const Duration(seconds: 30),
  );
}

/// Uygulama öne gelince: iki taraf aynı anda senk yapıp yenileme
/// belirtecini iki kez döndürmesin.
Future<void> cancelBackgroundSync() async {
  if (!_supported) return;
  await Workmanager().cancelByUniqueName(backgroundSyncUniqueName);
}
