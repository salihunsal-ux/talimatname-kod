/// Kanıt kuyruğu: Spike C'nin cihaz yarısı (kamera hariç).
///
/// Ölçülen şey sıra ve sınırlar: kanıt cevaptan sonra gidiyor mu,
/// baytlar yüklenip doğrulanıyor mu, sınırlar cihazda uygulanıyor mu
/// (sunucu kuyruk sınırını yalnızca yayınlıyor, TC-054).
library;

import 'dart:convert';
import 'dart:io';

import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:talimatname_saha/api/api_client.dart';
import 'package:talimatname_saha/api/models.dart';
import 'package:talimatname_saha/queue/answer_queue.dart';
import 'package:talimatname_saha/queue/database.dart';

class FakeServer {
  FakeServer({
    this.duplicate = false,
    this.rejectCode,
    this.failUpload = false,
  });

  final bool duplicate;
  final String? rejectCode;
  bool failUpload;

  final calls = <String>[];
  final answers = <Map<String, dynamic>>[];
  final uploads = <String, List<int>>{};
  final completed = <String>[];

  http.Client get client => MockClient((istek) async {
    calls.add('${istek.method} ${istek.url.path}');
    if (istek.url.path.endsWith('/sync/batch')) {
      final govde = jsonDecode(istek.body) as Map<String, dynamic>;
      final cevaplar = (govde['answers'] as List<dynamic>)
          .cast<Map<String, dynamic>>();
      final kanitlar = (govde['evidence'] as List<dynamic>)
          .cast<Map<String, dynamic>>();
      answers.addAll(cevaplar);
      return http.Response(
        jsonEncode({
          'answers': [
            for (final c in cevaplar)
              {
                'answer_id': c['answer_id'],
                'outcome': 'accepted',
                'error': null,
              },
          ],
          'evidence': [
            for (final k in kanitlar)
              if (rejectCode != null)
                {
                  'evidence_id': k['evidence_id'],
                  'outcome': 'rejected',
                  'error': {
                    'type': 'urn:talimatname:$rejectCode',
                    'retryable': false,
                  },
                }
              else if (duplicate)
                {'evidence_id': k['evidence_id'], 'outcome': 'duplicate'}
              else
                {
                  'evidence_id': k['evidence_id'],
                  'outcome': 'accepted',
                  'upload_url': '/api/v1/uploads/${k['evidence_id']}',
                },
          ],
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (istek.method == 'PUT') {
      if (failUpload) throw Exception('ağ koptu');
      uploads[istek.url.pathSegments.last] = istek.bodyBytes;
      return http.Response('{}', 200);
    }
    if (istek.url.path.endsWith('/complete')) {
      completed.add(istek.url.pathSegments[istek.url.pathSegments.length - 2]);
      return http.Response('{}', 200);
    }
    return http.Response('{}', 404);
  });
}

const _policy = QueuePolicy(
  maxEvidencePerItem: 3,
  maxEvidenceBytes: 3145728,
  queueEvidenceLimit: 4,
  queueHours: 72,
  batchAnswerLimit: 200,
  batchEvidenceLimit: 2,
);

void main() {
  late Directory dizin;
  late QueueDatabase db;

  AnswerQueue kur(FakeServer sunucu) => AnswerQueue(
    db: db,
    api: ApiClient(baseUrl: 'http://test/api/v1', client: sunucu.client),
    deviceId: 'cihaz-1',
    evidenceDir: dizin,
  );

  setUp(() {
    dizin = Directory.systemTemp.createTempSync('kanit_test_');
    db = QueueDatabase(NativeDatabase.memory());
  });
  tearDown(() async {
    await db.close();
    if (dizin.existsSync()) dizin.deleteSync(recursive: true);
  });

  List<int> foto(int tohum) => List<int>.generate(64, (i) => (i * tohum) % 251);

  test('cevapsız maddeye fotoğraf eklenemez', () async {
    final queue = kur(FakeServer());

    final sonuc = await queue.addPhoto(
      runId: 'r1',
      itemId: 'i1',
      bytes: foto(1),
    );

    expect(sonuc, PhotoResult.needsAnswer);
  });

  test('fotoğraf: önce cevap, sonra niyet, yükleme, doğrulama', () async {
    final sunucu = FakeServer();
    final queue = kur(sunucu);
    await queue.answer(
      runId: 'r1',
      itemId: 'i1',
      state: 'failed',
      note: 'kırık',
    );
    expect(
      await queue.addPhoto(runId: 'r1', itemId: 'i1', bytes: foto(3)),
      PhotoResult.added,
    );

    final sonuc = await queue.sync(policy: _policy);

    expect(sonuc.ok, isTrue);
    expect(sonuc.uploaded, 1);
    expect(sonuc.remaining, 0);
    final kimlik = sunucu.uploads.keys.single;
    expect(sunucu.uploads[kimlik], foto(3), reason: 'baytlar aynen gitti');
    expect(sunucu.completed, [kimlik]);
    expect(sunucu.calls, [
      'POST /api/v1/sync/batch', // cevap
      'POST /api/v1/sync/batch', // kanıt niyeti
      'PUT /api/v1/uploads/$kimlik',
      'POST /api/v1/evidence/$kimlik/complete',
    ]);
    expect(sunucu.answers.single['evidence_count'], 1);
  });

  test('yüklenen fotoğrafın yerel kopyası silinir', () async {
    final queue = kur(FakeServer());
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');
    await queue.addPhoto(runId: 'r1', itemId: 'i1', bytes: foto(5));
    expect(dizin.listSync(), hasLength(1));

    await queue.sync(policy: _policy);

    expect(dizin.listSync(), isEmpty, reason: 'cihaz deposu sınırlı');
    expect(await db.evidenceCount('r1', 'i1'), 1, reason: 'sayı satırdan');
  });

  test('gönderilmiş cevaba fotoğraf eklenince cevap yeniden gider', () async {
    // Cevap kanıt sayısını beyan ediyor; sayı değişince sunucu bilmeli.
    final sunucu = FakeServer();
    final queue = kur(sunucu);
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');
    await queue.sync(policy: _policy);
    expect(sunucu.answers.single['evidence_count'], 0);

    await queue.addPhoto(runId: 'r1', itemId: 'i1', bytes: foto(7));
    await queue.sync(policy: _policy);

    expect(sunucu.answers, hasLength(2));
    expect(sunucu.answers.last['evidence_count'], 1);
    expect(sunucu.answers.last['answer_id'], sunucu.answers.first['answer_id']);
  });

  test('madde başına sınır cihazda uygulanır', () async {
    final queue = kur(FakeServer());
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');
    for (var i = 1; i <= 3; i++) {
      expect(
        await queue.addPhoto(
          runId: 'r1',
          itemId: 'i1',
          bytes: foto(i),
          policy: _policy,
        ),
        PhotoResult.added,
      );
    }

    final dorduncu = await queue.addPhoto(
      runId: 'r1',
      itemId: 'i1',
      bytes: foto(9),
      policy: _policy,
    );

    expect(dorduncu, PhotoResult.itemFull);
  });

  test('kuyruk sınırı dolunca yeni fotoğraf engellenir (TC-054)', () async {
    // Sunucu bu sınırı yalnızca yayınlıyor, zorlamıyor: Spike A bulgusu.
    final queue = kur(FakeServer());
    for (var m = 0; m < 2; m++) {
      await queue.answer(runId: 'r1', itemId: 'i$m', state: 'passed');
      for (var i = 0; i < 2; i++) {
        await queue.addPhoto(
          runId: 'r1',
          itemId: 'i$m',
          bytes: foto(m * 10 + i + 1),
          policy: _policy,
        );
      }
    }
    await queue.answer(runId: 'r1', itemId: 'i9', state: 'passed');

    final sonuc = await queue.addPhoto(
      runId: 'r1',
      itemId: 'i9',
      bytes: foto(99),
      policy: _policy,
    );

    expect(sonuc, PhotoResult.queueFull);
  });

  test('yükleme yarıda koparsa fotoğraf kuyrukta kalır, sonra gider', () async {
    final sunucu = FakeServer(failUpload: true);
    final queue = kur(sunucu);
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');
    await queue.addPhoto(runId: 'r1', itemId: 'i1', bytes: foto(11));

    final ilk = await queue.sync(policy: _policy);
    expect(ilk.ok, isFalse);
    expect(ilk.remaining, 1);
    expect(dizin.listSync(), hasLength(1), reason: 'dosya silinmedi');

    sunucu.failUpload = false;
    final ikinci = await queue.sync(policy: _policy);

    expect(ikinci.uploaded, 1);
    expect(ikinci.remaining, 0);
  });

  test('sunucu "tekrar" derse kuyruktan düşer, yüklenmez', () async {
    final sunucu = FakeServer(duplicate: true);
    final queue = kur(sunucu);
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');
    await queue.addPhoto(runId: 'r1', itemId: 'i1', bytes: foto(13));

    final sonuc = await queue.sync(policy: _policy);

    expect(sonuc.remaining, 0);
    expect(sunucu.uploads, isEmpty);
  });

  test('kalıcı ret kuyruğu tıkamaz', () async {
    final sunucu = FakeServer(rejectCode: 'kanit-siniri');
    final queue = kur(sunucu);
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');
    await queue.addPhoto(runId: 'r1', itemId: 'i1', bytes: foto(17));

    final sonuc = await queue.sync(policy: _policy);
    await queue.sync(policy: _policy);

    expect(sonuc.rejected, 1);
    expect(sonuc.remaining, 0, reason: 'kalıcı ret bekleyen sayılmaz');
    expect(
      sunucu.calls.where((c) => c.endsWith('/sync/batch')),
      hasLength(2),
      reason: 'ikinci turda yeniden gönderilmedi',
    );
    final satir = (await db.evidenceForRun('r1')).single;
    expect(satir.lastErrorCode, 'kanit-siniri');
  });

  test('fotoğraflar parti sınırına göre dilimlenir', () async {
    final sunucu = FakeServer();
    final queue = kur(sunucu);
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');
    for (var i = 1; i <= 3; i++) {
      await queue.addPhoto(runId: 'r1', itemId: 'i1', bytes: foto(i));
    }

    final sonuc = await queue.sync(policy: _policy);

    expect(sonuc.uploaded, 3);
    // 1 cevap partisi + 2 kanıt partisi (2 + 1).
    expect(sunucu.calls.where((c) => c.endsWith('/sync/batch')), hasLength(3));
  });

  test('cihazdan çıkmamış fotoğraf kaldırılabilir', () async {
    final sunucu = FakeServer();
    final queue = kur(sunucu);
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');
    await queue.addPhoto(runId: 'r1', itemId: 'i1', bytes: foto(21));
    await queue.addPhoto(runId: 'r1', itemId: 'i1', bytes: foto(22));
    final ilk = (await db.evidenceForRun('r1')).first;

    expect(await queue.removePhoto(ilk.evidenceId), isTrue);

    expect(await db.evidenceCount('r1', 'i1'), 1);
    expect(dizin.listSync(), hasLength(1), reason: 'dosyası da silindi');
    await queue.sync(policy: _policy);
    expect(sunucu.answers.last['evidence_count'], 1);
    expect(sunucu.uploads, hasLength(1), reason: 'kaldırılan kare gitmedi');
  });

  test('yüklenmiş kanıt kaldırılamaz', () async {
    // Sunucuya ulaşan kanıt değiştirilemez kayıttır (FR-0609).
    final queue = kur(FakeServer());
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');
    await queue.addPhoto(runId: 'r1', itemId: 'i1', bytes: foto(23));
    await queue.sync(policy: _policy);
    final kayit = (await db.evidenceForRun('r1')).single;

    expect(await queue.removePhoto(kayit.evidenceId), isFalse);

    expect(await db.evidenceCount('r1', 'i1'), 1);
    expect(
      await queue.pendingCount(),
      0,
      reason: 'cevap yeniden kuyruğa girmedi',
    );
  });

  test('kaldırılan karenin yeri yeniden kullanılabilir', () async {
    final queue = kur(FakeServer());
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');
    for (var i = 1; i <= 3; i++) {
      await queue.addPhoto(
        runId: 'r1',
        itemId: 'i1',
        bytes: foto(30 + i),
        policy: _policy,
      );
    }
    final biri = (await db.evidenceForRun('r1')).first;
    await queue.removePhoto(biri.evidenceId);

    final sonuc = await queue.addPhoto(
      runId: 'r1',
      itemId: 'i1',
      bytes: foto(40),
      policy: _policy,
    );

    expect(sonuc, PhotoResult.added);
  });
}
