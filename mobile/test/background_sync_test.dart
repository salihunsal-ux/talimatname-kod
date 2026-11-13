/// Arka plan işinin kararı: ne zaman bitti, ne zaman yeniden denensin.
library;

import 'dart:convert';

import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:talimatname_saha/api/api_client.dart';
import 'package:talimatname_saha/background/sync_worker.dart';
import 'package:talimatname_saha/queue/answer_queue.dart';
import 'package:talimatname_saha/queue/database.dart';

void main() {
  late QueueDatabase db;
  var istek = 0;

  AnswerQueue kur(Future<http.Response> Function(http.Request) yanit) =>
      AnswerQueue(
        db: db,
        api: ApiClient(
          baseUrl: 'http://test/api/v1',
          client: MockClient((i) {
            istek++;
            return yanit(i);
          }),
        ),
        deviceId: 'cihaz-1',
      );

  setUp(() {
    db = QueueDatabase(NativeDatabase.memory());
    istek = 0;
  });
  tearDown(() => db.close());

  Future<http.Response> kabul(http.Request i) async {
    final govde = jsonDecode(i.body) as Map<String, dynamic>;
    return http.Response(
      jsonEncode({
        'answers': [
          for (final c in govde['answers'] as List<dynamic>)
            {
              'answer_id': (c as Map<String, dynamic>)['answer_id'],
              'outcome': 'accepted',
              'error': null,
            },
        ],
        'evidence': <Object>[],
      }),
      200,
      headers: {'content-type': 'application/json'},
    );
  }

  test('bekleyen yoksa sunucuya gidilmez', () async {
    final queue = kur(kabul);

    expect(await drainQueue(queue), isTrue);
    expect(istek, 0);
  });

  test('gönderilince iş biter', () async {
    final queue = kur(kabul);
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');

    expect(await drainQueue(queue), isTrue);
    expect(await queue.pendingCount(), 0);
  });

  test('ağ yoksa yeniden denenir, kayıt kuyrukta kalır', () async {
    final queue = kur((_) async => throw Exception('ağ yok'));
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');

    expect(
      await drainQueue(queue),
      isFalse,
      reason: 'Android geri çekilip dener',
    );
    expect(await queue.pendingCount(), 1);
  });

  test('sunucu reddederse yeniden denenmez', () async {
    // Aynı isteği arka planda tekrar tekrar göndermek pili harcar ve
    // aynı cevabı alır; kayıt kullanıcı uygulamayı açınca görünür.
    final queue = kur(
      (_) async => http.Response(
        jsonEncode({'type': 'urn:talimatname:yetki-yok', 'status': 403}),
        403,
        headers: {'content-type': 'application/problem+json'},
      ),
    );
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');

    expect(await drainQueue(queue), isTrue);
    expect(await queue.pendingCount(), 1, reason: 'kayıt silinmedi');
  });
}
