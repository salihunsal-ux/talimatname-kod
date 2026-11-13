/// Senk bitince ekranın gördüğü kuyruk satırları tazeleniyor mu.
///
/// Emülatörde görülen kusurun testi: gönderilmiş cevap ekranda
/// "Gönderilmeyi bekliyor" kalıyordu, üst bant ise "Hepsi gönderildi"
/// diyordu. İki gösterge aynı kuyruğu okuyup farklı şey söylüyordu.
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

void main() {
  test('senkten sonra satır "gönderildi" olarak okunur', () async {
    final db = QueueDatabase(NativeDatabase.memory());
    addTearDown(db.close);
    final client = MockClient((istek) async {
      final govde = jsonDecode(istek.body) as Map<String, dynamic>;
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
    });
    final queue = AnswerQueue(
      db: db,
      api: ApiClient(baseUrl: 'http://test/api/v1', client: client),
      deviceId: 'cihaz-1',
    );
    final container = ProviderContainer(
      overrides: [answerQueueProvider.overrideWith((ref) async => queue)],
    );
    addTearDown(container.dispose);

    await queue.answer(runId: 'r1', itemId: 'i1', state: 'passed');
    final once = await container.read(queuedForRunProvider('r1').future);
    expect(once.single.sent, isFalse);

    await container.read(syncProvider)();

    final sonra = await container.read(queuedForRunProvider('r1').future);
    expect(sonra.single.sent, isTrue, reason: 'ekran eski satırı göstermemeli');
    expect(await container.read(pendingCountProvider.future), 0);
  });
}
