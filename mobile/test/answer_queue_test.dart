/// Çevrimdışı kuyruk: Spike A'nın istemci yarısı.
///
/// Sunucu yarısı `api/tests/test_spike_a_senk.py` ile ölçüldü; orada
/// sunucunun sözleşmeye uyduğu görüldü. Buradaki soru tersi: **cihaz**
/// o sözleşmeye uyuyor mu — kayıp var mı, çift kayıt açıyor mu, parti
/// sınırını aşıyor mu, ret gelince kuyruğu tıkıyor mu.
///
/// Veritabanı bellekte (`NativeDatabase.memory`), sunucu sahte: ölçülen
/// şey istemcinin davranışı.
library;

import 'dart:convert';

import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:talimatname_saha/api/api_client.dart';
import 'package:talimatname_saha/api/models.dart';
import 'package:talimatname_saha/queue/answer_queue.dart';
import 'package:talimatname_saha/queue/database.dart';

/// Gönderilen partileri kaydeden sahte sunucu.
class FakeServer {
  FakeServer({this.reject = const {}, this.failAfter});

  /// `answer_id` -> ret kodu.
  final Map<String, String> reject;

  /// Bu kadar partiden sonra ağ kopar.
  final int? failAfter;

  final batches = <List<Map<String, dynamic>>>[];
  final stored = <String, Map<String, dynamic>>{};

  http.Client get client => MockClient((istek) async {
    if (failAfter != null && batches.length >= failAfter!) {
      throw const _NetworkDown();
    }
    final govde = jsonDecode(istek.body) as Map<String, dynamic>;
    final answers = (govde['answers'] as List<dynamic>)
        .cast<Map<String, dynamic>>();
    batches.add(answers);

    final sonuc = <Map<String, dynamic>>[];
    for (final cevap in answers) {
      final id = cevap['answer_id'] as String;
      final kod = reject[id];
      if (kod != null) {
        sonuc.add({
          'answer_id': id,
          'outcome': 'rejected',
          'error': {'type': 'urn:talimatname:$kod', 'retryable': false},
        });
        continue;
      }
      final tekrar = stored.containsKey(id);
      stored[id] = cevap;
      sonuc.add({
        'answer_id': id,
        'outcome': tekrar ? 'duplicate' : 'accepted',
        'error': null,
      });
    }
    return http.Response(
      jsonEncode({'answers': sonuc, 'evidence': []}),
      200,
      headers: {'content-type': 'application/json'},
    );
  });
}

class _NetworkDown implements Exception {
  const _NetworkDown();
}

({QueueDatabase db, AnswerQueue queue}) _kur(FakeServer sunucu) {
  final db = QueueDatabase(NativeDatabase.memory());
  return (
    db: db,
    queue: AnswerQueue(
      db: db,
      api: ApiClient(baseUrl: 'http://test/api/v1', client: sunucu.client),
      deviceId: 'cihaz-1',
    ),
  );
}

const _policy = QueuePolicy(
  maxEvidencePerItem: 3,
  maxEvidenceBytes: 3145728,
  queueEvidenceLimit: 500,
  queueHours: 72,
  batchAnswerLimit: 5,
  batchEvidenceLimit: 50,
);

void main() {
  test('cevap önce kuyruğa yazılır, gönderim ayrı', () async {
    final sunucu = FakeServer();
    final (:db, :queue) = _kur(sunucu);
    addTearDown(db.close);

    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');

    expect(await queue.pendingCount(), 1);
    expect(sunucu.batches, isEmpty, reason: 'yazmak göndermek değildir');
  });

  test('aynı madde yeniden cevaplanınca ikinci kayıt açılmaz', () async {
    // TC-053: kimlik (run, item) için sabit. Çevrimdışıyken fikir
    // değiştiren personel sunucuda iki satır oluşturmamalı.
    final sunucu = FakeServer();
    final (:db, :queue) = _kur(sunucu);
    addTearDown(db.close);

    final ilk = await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');
    final ikinci = await queue.answer(
      runId: 'r1',
      itemId: 'i1',
      state: 'failed',
    );

    expect(ikinci, ilk);
    expect(await queue.pendingCount(), 1);
    final satir = (await queue.forRun('r1')).single;
    expect(satir.state, 'failed', reason: 'son cevap geçerli');
  });

  test('gönderilen kayıt kuyruktan düşer, tekrar gönderilmez', () async {
    final sunucu = FakeServer();
    final (:db, :queue) = _kur(sunucu);
    addTearDown(db.close);
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');

    final sonuc = await queue.sync(policy: _policy);
    final ikinciTur = await queue.sync(policy: _policy);

    expect(sonuc.accepted, 1);
    expect(sonuc.remaining, 0);
    expect(ikinciTur.accepted, 0);
    expect(
      sunucu.batches,
      hasLength(1),
      reason: 'ikinci turda gönderecek şey yok',
    );
  });

  test('gönderilmiş cevap değişirse yeniden gönderilir', () async {
    final sunucu = FakeServer();
    final (:db, :queue) = _kur(sunucu);
    addTearDown(db.close);
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');
    await queue.sync(policy: _policy);

    await queue.answer(runId: 'r1', itemId: 'i1', state: 'failed');
    final sonuc = await queue.sync(policy: _policy);

    expect(sonuc.accepted, 1);
    expect(sunucu.stored.values.single['state'], 'failed');
    expect(sunucu.stored, hasLength(1), reason: 'aynı kimlik, tek satır');
  });

  test('kuyruk parti sınırına göre dilimlenir', () async {
    // Sunucu sınırı aşan partide **bütün isteği** reddediyor (Spike A
    // bulgusu), yani dilimleme istemcinin sorumluluğu.
    final sunucu = FakeServer();
    final (:db, :queue) = _kur(sunucu);
    addTearDown(db.close);
    for (var i = 0; i < 12; i++) {
      await queue.answer(runId: 'r1', itemId: 'i$i', state: 'passed');
    }

    final sonuc = await queue.sync(policy: _policy);

    expect(sonuc.accepted, 12);
    expect(sonuc.remaining, 0);
    expect(sunucu.batches.map((b) => b.length).toList(), [5, 5, 2]);
  });

  test('sınır bilinmiyorsa sözleşmenin varsayılanı kullanılır', () async {
    final sunucu = FakeServer();
    final (:db, :queue) = _kur(sunucu);
    addTearDown(db.close);
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');

    await queue.sync();

    expect(sunucu.batches, hasLength(1));
  });

  test('ağ koparsa kayıt kuyrukta kalır', () async {
    // "Gönderildi" demek, gönderilmemişken en pahalı yalandır.
    final sunucu = FakeServer(failAfter: 0);
    final (:db, :queue) = _kur(sunucu);
    addTearDown(db.close);
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');

    final sonuc = await queue.sync(policy: _policy);

    expect(sonuc.ok, isFalse);
    expect(sonuc.failure!.isNetwork, isTrue);
    expect(sonuc.remaining, 1);
    expect(await queue.pendingCount(), 1);
  });

  test('yarıda kopan senkte gönderilenler kuyrukta kalmaz', () async {
    final sunucu = FakeServer(failAfter: 2);
    final (:db, :queue) = _kur(sunucu);
    addTearDown(db.close);
    for (var i = 0; i < 12; i++) {
      await queue.answer(runId: 'r1', itemId: 'i$i', state: 'passed');
    }

    final sonuc = await queue.sync(policy: _policy);

    expect(sonuc.ok, isFalse);
    expect(sonuc.accepted, 10, reason: 'iki parti gitti');
    expect(sonuc.remaining, 2, reason: 'kalan iki kayıt kuyrukta');
  });

  test('reddedilen kayıt kuyruğu tıkamaz, kod saklanır', () async {
    // Tek bozuk kayıt yüzünden döngüye girmek, kuyruğu sonsuza kadar
    // kilitlemek olurdu.
    final sunucu = FakeServer(reject: const {});
    final (:db, :queue) = _kur(sunucu);
    addTearDown(db.close);
    final kotu = await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');
    await queue.answer(runId: 'r1', itemId: 'i2', state: 'passed');
    final ikinciSunucu = FakeServer(reject: {kotu: 'pencere-kapali'});
    final queue2 = AnswerQueue(
      db: db,
      api: ApiClient(
        baseUrl: 'http://test/api/v1',
        client: ikinciSunucu.client,
      ),
      deviceId: 'cihaz-1',
    );

    final sonuc = await queue2.sync(policy: _policy);

    expect(sonuc.accepted, 1);
    expect(sonuc.rejected, 1);
    expect(
      ikinciSunucu.batches,
      hasLength(1),
      reason: 'aynı parti yeniden denenmedi',
    );
    final satir = (await db.forItem('r1', 'i1'))!;
    expect(satir.lastErrorCode, 'pencere-kapali');
    expect(satir.sent, isFalse);
  });

  test('hepsi reddedilirse döngüye girilmez', () async {
    final sunucu = FakeServer();
    final (:db, :queue) = _kur(sunucu);
    addTearDown(db.close);
    final id = await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');
    final retSunucu = FakeServer(reject: {id: 'pencere-kapali'});
    final queue2 = AnswerQueue(
      db: db,
      api: ApiClient(baseUrl: 'http://test/api/v1', client: retSunucu.client),
      deviceId: 'cihaz-1',
    );

    final sonuc = await queue2.sync(policy: _policy);

    expect(sonuc.rejected, 1);
    expect(retSunucu.batches, hasLength(1));
  });

  test('değer ve not sunucuya giden gövdeye geçiyor', () async {
    final sunucu = FakeServer();
    final (:db, :queue) = _kur(sunucu);
    addTearDown(db.close);
    await queue.answer(
      runId: 'r1',
      itemId: 'i1',
      state: 'failed',
      value: -21.5,
    );

    await queue.sync(policy: _policy);

    final gonderilen = sunucu.batches.single.single;
    expect(gonderilen['value'], -21.5);
    expect(gonderilen['state'], 'failed');
    expect(gonderilen['device_id'], 'cihaz-1');
    expect(gonderilen['answered_at'], isA<String>());
  });

  test('kuyruk uygulama kapanınca kalıcı', () async {
    // Drift dosyası paylaşıldığında aynı kayıtlar görünmeli: uçak
    // modunda doldurup uygulamayı kapatan personel veri kaybetmemeli.
    final sunucu = FakeServer();
    final db = QueueDatabase(NativeDatabase.memory());
    addTearDown(db.close);
    final ilk = AnswerQueue(
      db: db,
      api: ApiClient(baseUrl: 'http://test/api/v1', client: sunucu.client),
      deviceId: 'cihaz-1',
    );
    await ilk.answer(runId: 'r1', itemId: 'i1', state: 'passed');

    // Yeni "oturum": aynı veritabanı, yeni kuyruk nesnesi.
    final ikinci = AnswerQueue(
      db: db,
      api: ApiClient(baseUrl: 'http://test/api/v1', client: sunucu.client),
      deviceId: 'cihaz-1',
    );

    expect(await ikinci.pendingCount(), 1);
  });
}
