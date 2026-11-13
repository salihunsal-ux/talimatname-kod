/// Belge önbelleği: ağ yokken cihazdaki son kopya.
///
/// Emülatörde görülen eksiğin testi: uygulama çevrimdışı açılınca kuyruk
/// ve oturum duruyordu ama liste gelmiyordu.
library;

import 'dart:convert';

import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:talimatname_saha/api/api_client.dart';
import 'package:talimatname_saha/api/problem.dart';
import 'package:talimatname_saha/queue/database.dart';
import 'package:talimatname_saha/queue/doc_cache.dart';

void main() {
  late QueueDatabase db;
  var agVar = true;
  var yanit = http.Response(
    jsonEncode({'surum': 1}),
    200,
    headers: {'content-type': 'application/json'},
  );

  DocCache kur() => DocCache(
    db: db,
    api: ApiClient(
      baseUrl: 'http://test/api/v1',
      client: MockClient((_) async {
        if (!agVar) throw Exception('ağ yok');
        return yanit;
      }),
    ),
  );

  setUp(() {
    db = QueueDatabase(NativeDatabase.memory());
    agVar = true;
    yanit = http.Response(
      jsonEncode({'surum': 1}),
      200,
      headers: {'content-type': 'application/json'},
    );
  });
  tearDown(() => db.close());

  test('ağ varken sunucudan gelir ve saklanır', () async {
    final doc = await kur().get('/sync/manifest');

    expect(doc.stale, isFalse);
    expect(doc.json['surum'], 1);
    expect(await db.getDoc('/sync/manifest'), isNotNull);
  });

  test('ağ yokken son kopya gelir ve bayat olduğu söylenir', () async {
    final cache = kur();
    await cache.get('/sync/manifest');
    agVar = false;

    final doc = await cache.get('/sync/manifest');

    expect(doc.stale, isTrue, reason: 'ekran bunu kullanıcıya söylemeli');
    expect(doc.json['surum'], 1);
  });

  test('hiç kopya yoksa ağ hatası olduğu gibi çıkar', () async {
    agVar = false;

    await expectLater(
      kur().get('/sync/manifest'),
      throwsA(isA<ApiException>().having((h) => h.isNetwork, 'ağ', isTrue)),
    );
  });

  test('sunucu "hayır" dediyse eski kopya gösterilmez', () async {
    // 403/404 bir cevaptır, bağlantı sorunu değil: eski listeyi
    // göstermek artık doğru olmayan bir şeyi doğruymuş gibi sunar.
    final cache = kur();
    await cache.get('/runs/r1');
    yanit = http.Response(
      jsonEncode({'type': 'urn:talimatname:bulunamadi', 'status': 404}),
      404,
      headers: {'content-type': 'application/problem+json'},
    );

    await expectLater(
      cache.get('/runs/r1'),
      throwsA(isA<ApiException>().having((h) => h.statusCode, 'kod', 404)),
    );
  });

  test('yeni kopya eskisinin yerini alır', () async {
    final cache = kur();
    await cache.get('/sync/manifest');
    yanit = http.Response(
      jsonEncode({'surum': 2}),
      200,
      headers: {'content-type': 'application/json'},
    );
    await cache.get('/sync/manifest');
    agVar = false;

    expect((await cache.get('/sync/manifest')).json['surum'], 2);
  });

  test('çıkışta önbellek silinir', () async {
    final cache = kur();
    await cache.get('/sync/manifest');

    await db.clearDocs();
    agVar = false;

    await expectLater(
      cache.get('/sync/manifest'),
      throwsA(isA<ApiException>()),
    );
  });
}
