/// Önden indirme: hiç açılmamış liste çevrimdışı açılabilmeli.
library;

import 'dart:convert';

import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:talimatname_saha/api/api_client.dart';
import 'package:talimatname_saha/api/models.dart';
import 'package:talimatname_saha/queue/database.dart';
import 'package:talimatname_saha/queue/doc_cache.dart';
import 'package:talimatname_saha/queue/prefetch.dart';

final _simdi = DateTime.utc(2026, 11, 13, 9);

ManifestRun _run(String id, {required int acilis, String surum = 'v1'}) =>
    ManifestRun(
      runId: id,
      planName: 'Liste $id',
      branchName: 'Kadıköy',
      templateVersionId: surum,
      businessDay: '2026-11-13',
      status: 'scheduled',
      windowStart: _simdi.add(Duration(hours: acilis)),
      windowEnd: _simdi.add(Duration(hours: acilis + 1)),
      toleranceEnd: _simdi.add(Duration(hours: acilis + 1)),
      writableFrom: _simdi.add(Duration(hours: acilis)),
    );

Manifest _manifest(List<ManifestRun> runs) => Manifest(
  serverTime: _simdi,
  skewMinutes: null,
  skewFlagged: false,
  horizonHours: 48,
  refreshAfterMinutes: 15,
  runs: runs,
  policy: const QueuePolicy(
    maxEvidencePerItem: 3,
    maxEvidenceBytes: 3145728,
    queueEvidenceLimit: 500,
    queueHours: 72,
    batchAnswerLimit: 200,
    batchEvidenceLimit: 50,
  ),
);

void main() {
  late QueueDatabase db;
  late List<String> istekler;
  var agVar = true;

  DocCache kur() => DocCache(
    db: db,
    api: ApiClient(
      baseUrl: 'http://test/api/v1',
      client: MockClient((istek) async {
        if (!agVar) throw Exception('ağ yok');
        istekler.add(istek.url.path.replaceFirst('/api/v1', ''));
        return http.Response(
          jsonEncode({'yol': istek.url.path}),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    ),
  );

  setUp(() {
    db = QueueDatabase(NativeDatabase.memory());
    istekler = [];
    agVar = true;
  });
  tearDown(() => db.close());

  test('hedefler: açık olanlar ve 12 saat içinde açılacaklar', () {
    final manifest = _manifest([
      _run('gecmis', acilis: -3), // penceresi kapandı
      _run('acik', acilis: 0),
      _run('aksam', acilis: 11),
      _run('yarin', acilis: 26),
    ]);

    final hedefler = prefetchTargets(manifest, _simdi);

    expect(hedefler.map((r) => r.runId), ['acik', 'aksam']);
  });

  test('görünüm ve sürüm iner; aynı sürüm bir kez', () async {
    final manifest = _manifest([
      _run('r1', acilis: 0),
      _run('r2', acilis: 2),
      _run('r3', acilis: 4, surum: 'v2'),
    ]);

    final indirilen = await prefetchRuns(kur(), manifest, _simdi);

    expect(indirilen, 5);
    expect(istekler, [
      '/runs/r1',
      '/template-versions/v1',
      '/runs/r2',
      '/runs/r3',
      '/template-versions/v2',
    ]);
  });

  test('önden inen liste çevrimdışı açılır', () async {
    // Asıl senaryo: personel listeyi hiç açmadı, bağlantı gitti.
    final cache = kur();
    await prefetchRuns(cache, _manifest([_run('r1', acilis: 0)]), _simdi);
    agVar = false;

    final gorunum = await cache.get('/runs/r1');
    final surum = await cache.get('/template-versions/v1');

    expect(gorunum.stale, isTrue);
    expect(surum.stale, isTrue);
  });

  test('taze kopya varken yeniden indirilmez', () async {
    final cache = kur();
    final manifest = _manifest([_run('r1', acilis: 0)]);
    await prefetchRuns(cache, manifest, _simdi);
    istekler.clear();

    final ikinci = await prefetchRuns(cache, manifest, _simdi);

    expect(ikinci, 0, reason: 'manifest her tazelendiğinde hepsi çekilmez');
    expect(istekler, isEmpty);
  });

  test('ağ koparsa sessizce durur, inenler kalır', () async {
    final cache = kur();
    await prefetchRuns(cache, _manifest([_run('r1', acilis: 0)]), _simdi);
    agVar = false;

    final sonuc = await prefetchRuns(
      cache,
      _manifest([_run('r1', acilis: 0), _run('r2', acilis: 1)]),
      _simdi,
    );

    expect(sonuc, 0);
    expect(await db.getDoc('/runs/r1'), isNotNull);
    expect(await db.getDoc('/runs/r2'), isNull);
  });
}
