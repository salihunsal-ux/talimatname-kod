/// Listeyi gönderme akışı.
///
/// Üç şeyi kilitliyor: kuyruk boşalmadan gönderilmiyor, eksikleri cihaz
/// değil **sunucu** söylüyor, ve başarı sunucunun verdiği sonuçla
/// bildiriliyor.
library;

import 'dart:convert';

import 'package:drift/native.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:talimatname_saha/api/api_client.dart';
import 'package:talimatname_saha/queue/answer_queue.dart';
import 'package:talimatname_saha/queue/database.dart';
import 'package:talimatname_saha/state/providers.dart';
import 'package:talimatname_saha/state/run_providers.dart';

Map<String, dynamic> _view({
  String status = 'in_progress',
  List<Map<String, dynamic>> blockers = const [],
  String? result,
  num? score,
}) => {
  'run_id': 'r1',
  'branch_id': 'b1',
  'branch_name': 'Kadıköy',
  'business_day': '2026-11-13',
  'status': status,
  'result': result,
  'score_percent': score,
  'window_start': '2026-11-13T07:00:00+00:00',
  'window_end': '2026-11-13T07:15:00+00:00',
  'tolerance_end': '2026-11-13T07:15:00+00:00',
  'writable_from': '2026-11-13T06:45:00+00:00',
  'template_name': 'Tuvalet',
  'sections': <Object>[],
  'blockers': blockers,
};

http.Response _json(Object body, [int status = 200]) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

({ProviderContainer container, AnswerQueue queue, List<String> calls}) _kur(
  Future<http.Response> Function(http.Request) handler,
) {
  final calls = <String>[];
  final client = MockClient((istek) {
    calls.add('${istek.method} ${istek.url.path}');
    return handler(istek);
  });
  final api = ApiClient(baseUrl: 'http://test/api/v1', client: client);
  final db = QueueDatabase(NativeDatabase.memory());
  final queue = AnswerQueue(db: db, api: api, deviceId: 'cihaz-1');
  final container = ProviderContainer(
    overrides: [
      apiClientProvider.overrideWithValue(api),
      answerQueueProvider.overrideWith((ref) async => queue),
    ],
  );
  addTearDown(() async {
    container.dispose();
    await db.close();
  });
  return (container: container, queue: queue, calls: calls);
}

Future<http.Response> _kabul(http.Request istek) async {
  final govde = jsonDecode(istek.body) as Map<String, dynamic>;
  return _json({
    'answers': [
      for (final c in govde['answers'] as List<dynamic>)
        {
          'answer_id': (c as Map<String, dynamic>)['answer_id'],
          'outcome': 'accepted',
          'error': null,
        },
    ],
    'evidence': <Object>[],
  });
}

void main() {
  test('önce kuyruk boşalır, sonra gönderilir', () async {
    final (:container, :queue, :calls) = _kur((istek) async {
      if (istek.url.path.endsWith('/sync/batch')) return _kabul(istek);
      return _json(_view(status: 'submitted', result: 'passed', score: 100));
    });
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');

    final sonuc = await container.read(submitProvider)('r1');

    expect(sonuc, isA<SubmitDone>());
    expect((sonuc as SubmitDone).view.result, 'passed');
    expect(sonuc.view.scorePercent, 100);
    expect(calls, ['POST /api/v1/sync/batch', 'POST /api/v1/runs/r1/submit']);
  });

  test('kuyruk boşalmadıysa sunucudan gönderim istenmez', () async {
    // Bekleyen cevap varken göndermek, sunucunun görmediği cevaplarla
    // puan hesaplatmak olurdu.
    final (:container, :queue, :calls) = _kur(
      (_) async => throw Exception('ağ yok'),
    );
    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');

    final sonuc = await container.read(submitProvider)('r1');

    expect(sonuc, isA<SubmitNeedsNetwork>());
    expect(calls.where((c) => c.endsWith('/submit')), isEmpty);
    expect(await queue.pendingCount(), 1, reason: 'cevap cihazda duruyor');
  });

  test('eksikleri sunucu söyler', () async {
    final (:container, queue: _, :calls) = _kur((istek) async {
      if (istek.url.path.endsWith('/submit')) {
        return _json({
          'type': 'urn:talimatname:eksik-var',
          'title': 'Eksik var',
          'status': 422,
        }, 422);
      }
      return _json(
        _view(
          blockers: [
            {'item_id': 'i2', 'title': 'Zemin kuru', 'kind': 'unanswered'},
            {'item_id': 'i3', 'title': 'Koku uygun', 'kind': 'note'},
          ],
        ),
      );
    });

    final sonuc = await container.read(submitProvider)('r1');

    expect(sonuc, isA<SubmitBlocked>());
    final eksikler = (sonuc as SubmitBlocked).blockers;
    expect(eksikler.map((e) => e.kind), ['unanswered', 'note']);
    expect(calls, ['POST /api/v1/runs/r1/submit', 'GET /api/v1/runs/r1']);
  });

  test('başka ret eksik sanılmaz', () async {
    // Pencere kapandıysa "eksik var" demek kullanıcıyı boşuna
    // maddelere geri gönderir.
    final (:container, queue: _, calls: _) = _kur(
      (istek) async => _json({
        'type': 'urn:talimatname:pencere-kapali',
        'title': 'Pencere kapandı',
        'status': 409,
      }, 409),
    );

    final sonuc = await container.read(submitProvider)('r1');

    expect(sonuc, isA<SubmitRejected>());
    expect((sonuc as SubmitRejected).error.code, 'pencere-kapali');
  });
}
