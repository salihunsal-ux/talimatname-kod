/// Sözleşmenin cihaz tarafı: problem+json, oturum ve manifest.
///
/// Gövdeler **gerçek sunucudan** alınmış şekle göre yazıldı (alan
/// adları `run_id`, `full_name`, `expires_in_minutes`, alan hatasında
/// `alan`/`sebep`); uydurulmuş bir şema test etmek, testin geçip
/// uygulamanın çökmesi demek olur.
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:talimatname_saha/api/api_client.dart';
import 'package:talimatname_saha/api/models.dart';
import 'package:talimatname_saha/api/problem.dart';

const _sessionBody = {
  'access_token': 'at-1',
  'token_type': 'bearer',
  'expires_in_minutes': 30,
  'refresh_token': 'rt-1',
  'refresh_expires_at': '2026-12-12T18:00:00+00:00',
  'user': {
    'id': 'b1b1b1b1-0000-0000-0000-000000000001',
    'full_name': 'Ayşe Şube',
    'phone': '+905321110003',
    'roles': [
      {
        'role': 'branch_manager',
        'role_label': 'Şube müdürü',
        'scope_type': 'branch',
        'scope_id': 'c1c1c1c1-0000-0000-0000-000000000001',
      },
    ],
  },
};

Map<String, dynamic> _manifestBody({required String writableFrom}) => {
  'clock': {
    'server_time': '2026-11-12T18:00:00+00:00',
    'device_time': null,
    'skew_minutes': null,
    'flagged': false,
  },
  'horizon_hours': 48,
  'refresh_after_minutes': 15,
  'runs': [
    {
      'run_id': 'd1d1d1d1-0000-0000-0000-000000000001',
      'plan_id': 'd2d2d2d2-0000-0000-0000-000000000001',
      'plan_name': 'Günlük kapanış',
      'branch_id': 'c1c1c1c1-0000-0000-0000-000000000001',
      'branch_code': 'KDK',
      'branch_name': 'Kadıköy',
      'template_version_id': 'e1e1e1e1-0000-0000-0000-000000000001',
      'business_day': '2026-11-12',
      'status': 'scheduled',
      'window_start': '2026-11-12T19:00:00+00:00',
      'window_end': '2026-11-12T20:00:00+00:00',
      'tolerance_end': '2026-11-12T21:00:00+00:00',
      'writable_from': writableFrom,
    },
  ],
  'template_versions': [
    {
      'id': 'e1e1e1e1-0000-0000-0000-000000000001',
      'template_id': 'e2e2e2e2-0000-0000-0000-000000000001',
      'version_no': 3,
      'published_at': '2026-11-01T08:00:00+00:00',
      'item_count': 7,
    },
  ],
  'not_done_reasons': [
    {'code': 'no_time', 'label': 'Zaman yetmedi'},
  ],
  'policy': {
    'max_evidence_per_item': 3,
    'max_evidence_bytes': 3145728,
    'queue_evidence_limit': 500,
    'queue_hours': 72,
    'batch_answer_limit': 200,
    'batch_evidence_limit': 50,
  },
};

void main() {
  group('problem+json', () {
    test('type URN’den kod çıkarılır', () {
      final hata = ApiException.parse(
        409,
        jsonEncode({
          'type': 'urn:talimatname:pencere-kapali',
          'title': 'Pencere kapandı',
          'status': 409,
        }),
      );

      expect(hata.code, 'pencere-kapali');
      expect(hata.retryable, isFalse);
    });

    test('alan hataları okunur (alan/sebep)', () {
      final hata = ApiException.parse(
        422,
        jsonEncode({
          'type': 'urn:talimatname:gecersiz-istek',
          'title': 'Geçersiz istek',
          'status': 422,
          'errors': [
            {'alan': 'answers', 'sebep': 'En fazla 200 öğe olabilir'},
          ],
        }),
      );

      expect(hata.fieldErrors.single.field, 'answers');
      expect(hata.fieldErrors.single.reason, 'En fazla 200 öğe olabilir');
    });

    test('problem+json olmayan gövde çökmez', () {
      // Vekil sunucu 502'de HTML döndürebilir; istemci bunu
      // "bilinmeyen ama tekrar denenebilir" olarak görmeli.
      final hata = ApiException.parse(502, '<html>Bad Gateway</html>');

      expect(hata.code, 'bilinmeyen');
      expect(hata.retryable, isTrue);
    });
  });

  group('oturum', () {
    test('expires_in_minutes son kullanma anına çevrilir', () {
      final now = DateTime.utc(2026, 11, 12, 18);

      final session = Session.fromJson(_sessionBody, now: now);

      expect(session.expiresAt, DateTime.utc(2026, 11, 12, 18, 30));
      expect(session.fullName, 'Ayşe Şube');
      expect(session.roles, ['branch_manager']);
    });

    test('yenileme kararı kalan süreye göre', () {
      // Oturum **gerçek** saate göre kuruluyor: sabit bir "şimdi" ile
      // kurup gerçek saatle sorgulamak, testi koşma saatine bağlar.
      final taze = Session.fromJson(_sessionBody, now: DateTime.now());
      final bayat = Session.fromJson({
        ..._sessionBody,
        'expires_in_minutes': 0,
      }, now: DateTime.now().subtract(const Duration(minutes: 5)));

      expect(taze.needsRefresh, isFalse);
      expect(bayat.needsRefresh, isTrue);
    });

    test('saklanan şekil gidip geri geliyor', () {
      final session = Session.fromJson(_sessionBody, now: DateTime.utc(2026));

      final geri = Session.fromStored(session.toStored());

      expect(geri.accessToken, session.accessToken);
      expect(geri.refreshToken, session.refreshToken);
      expect(geri.expiresAt, session.expiresAt);
      expect(geri.roles, session.roles);
    });
  });

  group('istemci', () {
    test('401 bir kez yenileyip isteği tekrarlar', () async {
      final istekler = <String>[];
      final client = MockClient((istek) async {
        istekler.add('${istek.method} ${istek.url.path}');
        if (istek.url.path.endsWith('/auth/refresh')) {
          return http.Response(
            jsonEncode({..._sessionBody, 'access_token': 'at-2'}),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (istek.headers['Authorization'] == 'Bearer at-2') {
          return http.Response(
            jsonEncode(
              _manifestBody(writableFrom: '2026-11-12T18:45:00+00:00'),
            ),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response(
          jsonEncode({
            'type': 'urn:talimatname:oturum-gecersiz',
            'status': 401,
          }),
          401,
          headers: {'content-type': 'application/problem+json'},
        );
      });
      final api = ApiClient(baseUrl: 'http://test/api/v1', client: client)
        ..adopt(Session.fromJson(_sessionBody, now: DateTime.now()));

      final manifest = await api.manifest();

      expect(manifest.runs.single.planName, 'Günlük kapanış');
      expect(istekler, [
        'GET /api/v1/sync/manifest',
        'POST /api/v1/auth/refresh',
        'GET /api/v1/sync/manifest',
      ]);
    });

    test('ikinci 401 sonsuz döngüye girmez', () async {
      var yenileme = 0;
      final client = MockClient((istek) async {
        if (istek.url.path.endsWith('/auth/refresh')) {
          yenileme++;
          return http.Response(
            jsonEncode(_sessionBody),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response(
          jsonEncode({
            'type': 'urn:talimatname:oturum-gecersiz',
            'status': 401,
          }),
          401,
          headers: {'content-type': 'application/problem+json'},
        );
      });
      final api = ApiClient(baseUrl: 'http://test/api/v1', client: client)
        ..adopt(Session.fromJson(_sessionBody, now: DateTime.now()));

      await expectLater(api.manifest(), throwsA(isA<ApiException>()));
      expect(yenileme, 1, reason: 'yenileme bir kez denenmeli');
    });

    test('yenileme reddedilirse oturum düşer', () async {
      // Çalıştırınca görüldü: sunucu yenilemeyi 403'leyince uygulama
      // her sağlayıcı için yeniden deniyordu — tek açılışta 29 istek.
      var dusen = 0;
      var istek = 0;
      final client = MockClient((_) async {
        istek++;
        return http.Response(
          jsonEncode({
            'type': 'urn:talimatname:oturum-gecersiz',
            'status': 403,
          }),
          403,
          headers: {'content-type': 'application/problem+json'},
        );
      });
      final api = ApiClient(
        baseUrl: 'http://test/api/v1',
        client: client,
        onSessionChanged: (s) {
          if (s == null) dusen++;
        },
      )..adopt(Session.fromJson(_sessionBody, now: DateTime.now()));

      await expectLater(api.refresh(), throwsA(isA<ApiException>()));

      expect(dusen, 1, reason: 'oturum bırakıldı');
      expect(api.session, isNull);
      await expectLater(api.refresh(), throwsA(isA<ApiException>()));
      expect(istek, 1, reason: 'elde oturum yokken sunucuya gidilmez');
    });

    test('ağ hatası ApiException.network olur', () async {
      final client = MockClient((_) => throw const SocketLikeError());
      final api = ApiClient(baseUrl: 'http://test/api/v1', client: client);

      try {
        await api.requestCode('+905321110003');
        fail('hata beklendi');
      } on ApiException catch (hata) {
        expect(hata.isNetwork, isTrue);
        expect(hata.retryable, isTrue);
        expect(hata.code, 'aglanamadi');
      }
    });
  });

  group('manifest', () {
    test('parti sınırları okunur (Spike A bulgusu)', () {
      final manifest = Manifest.fromJson(
        _manifestBody(writableFrom: '2026-11-12T18:45:00+00:00'),
      );

      expect(manifest.policy.batchAnswerLimit, 200);
      expect(manifest.policy.batchEvidenceLimit, 50);
      expect(manifest.policy.queueEvidenceLimit, 500);
    });

    test('writable_from gelmeden yazılabilir sayılmaz (BR-02a)', () {
      final manifest = Manifest.fromJson(
        _manifestBody(writableFrom: '2026-11-12T18:45:00+00:00'),
      );
      final run = manifest.runs.single;

      expect(run.writableAt(DateTime.utc(2026, 11, 12, 18, 30)), isFalse);
      expect(run.openedBy(DateTime.utc(2026, 11, 12, 18, 30)), isFalse);
      expect(run.writableAt(DateTime.utc(2026, 11, 12, 18, 50)), isTrue);
    });

    test('tolerans bitince yazılabilir değil', () {
      final manifest = Manifest.fromJson(
        _manifestBody(writableFrom: '2026-11-12T18:45:00+00:00'),
      );
      final run = manifest.runs.single;

      expect(run.writableAt(DateTime.utc(2026, 11, 12, 21, 1)), isFalse);
      expect(run.openedBy(DateTime.utc(2026, 11, 12, 21, 1)), isTrue);
    });
  });
}

/// `http` paketinin attığı ağ hatasının yerine geçen basit tür.
class SocketLikeError implements Exception {
  const SocketLikeError();

  @override
  String toString() => 'bağlantı kurulamadı';
}
