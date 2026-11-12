/// Sunucuya bakan tek yüz.
///
/// Sorumluluğu: adres, belirteç, yenileme ve problem+json. Ekranlar
/// `http` paketini görmez — çevrimdışı kuyruk (Drift) araya girince
/// değişecek yer burası olacak.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';
import 'problem.dart';
import 'run_models.dart';

/// Derleme zamanında verilir:
/// `flutter run --dart-define=API_BASE=https://demo.talimatname.com/api/v1`
///
/// Varsayılan **yerel** API: demoya kazara yazmamak için. Demo adresi
/// açıkça verilmeli.
const apiBaseFromEnv = String.fromEnvironment(
  'API_BASE',
  defaultValue: 'http://localhost:8000/api/v1',
);

class ApiClient {
  ApiClient({String? baseUrl, http.Client? client, this.onSessionChanged})
    : baseUrl = baseUrl ?? apiBaseFromEnv,
      _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;

  /// Yenileme sonrası yeni oturumu saklamak için.
  final void Function(Session?)? onSessionChanged;

  Session? _session;
  Session? get session => _session;

  void adopt(Session? session) {
    _session = session;
  }

  /// `POST /auth/request-code`. Demo ve geliştirme kurulumunda yanıt
  /// `dev_code` taşıyor; üretimde taşımaz ve `null` döner.
  Future<String?> requestCode(String phone) async {
    final body = await _send(
      'POST',
      '/auth/request-code',
      body: {'phone': phone},
      authenticated: false,
    );
    return body['dev_code'] as String?;
  }

  Future<Session> verify(String phone, String code) async {
    final body = await _send(
      'POST',
      '/auth/verify',
      body: {'phone': phone, 'code': code},
      authenticated: false,
    );
    final session = Session.fromJson(body);
    _session = session;
    onSessionChanged?.call(session);
    return session;
  }

  Future<Session> refresh() async {
    final current = _session;
    if (current == null || !current.refreshUsable) {
      throw ApiException(statusCode: 401, type: '${urnPrefix}oturum-yok');
    }
    final Map<String, dynamic> body;
    try {
      body = await _send(
        'POST',
        '/auth/refresh',
        body: {'refresh_token': current.refreshToken},
        authenticated: false,
      );
    } on ApiException catch (hata) {
      // Yenileme **reddedildiyse** oturum bitmiştir: belirteç iptal
      // edilmiş, sunucu anahtarı değişmiş ya da süresi dolmuş olabilir.
      // Elde tutup her istekte yeniden denemek, kullanıcıyı boş ekranda
      // bırakırken sunucuyu dövmek olurdu — çalıştırınca görüldü:
      // tek açılışta 29 istek gitti.
      if (hata.isUnauthorized) {
        _session = null;
        onSessionChanged?.call(null);
      }
      rethrow;
    }
    final session = Session.fromJson(body);
    _session = session;
    onSessionChanged?.call(session);
    return session;
  }

  Future<void> signOut() async {
    final current = _session;
    _session = null;
    onSessionChanged?.call(null);
    if (current == null) return;
    try {
      await _send(
        'POST',
        '/auth/logout',
        body: {'refresh_token': current.refreshToken},
        authenticated: false,
      );
    } on ApiException {
      // Sunucuya ulaşılamasa da yerel oturum düştü: kullanıcı çıkmak
      // istedi, bunu ağ hatasına bağlamak yanlış olur.
    }
  }

  Future<Manifest> manifest() async {
    final body = await _send('GET', '/sync/manifest');
    return Manifest.fromJson(body);
  }

  Future<RunView> run(String runId) async =>
      RunView.fromJson(await _send('GET', '/runs/$runId'));

  /// Şablon sürümünün maddeleri. Yayınlanmış sürüm değişmiyor (BR-18),
  /// yani çağıran sonucu süresiz önbelleğe alabilir.
  Future<Map<String, VersionItem>> templateVersion(String versionId) async =>
      VersionItem.mapFromJson(
        await _send('GET', '/template-versions/$versionId'),
      );

  /// Kuyruğu gönderir. Yanıt **200** ve sonuç kayıt başına; bu yüzden
  /// dönen satırlar tek tek okunur, istek bütün olarak başarılı
  /// sayılmaz.
  Future<BatchResult> syncAnswers(List<Map<String, dynamic>> answers) async {
    final body = await _send(
      'POST',
      '/sync/batch',
      body: {
        'answers': answers,
        'evidence': const <Map<String, dynamic>>[],
        'device_time': DateTime.now().toUtc().toIso8601String(),
      },
    );
    return BatchResult.fromJson(body);
  }

  Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Map<String, dynamic>? body,
    bool authenticated = true,
    bool allowRefresh = true,
  }) async {
    if (authenticated && (_session?.needsRefresh ?? false)) {
      await refresh();
    }

    final request = http.Request(method, Uri.parse('$baseUrl$path'));
    request.headers['Accept'] = 'application/json';
    if (body != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    final token = _session?.accessToken;
    if (authenticated && token != null) {
      request.headers['Authorization'] = 'Bearer $token';
    }

    http.Response response;
    try {
      response = await http.Response.fromStream(await _client.send(request));
    } on Object catch (hata) {
      throw ApiException.network(hata);
    }

    if (response.statusCode == 401 && authenticated && allowRefresh) {
      // Cihaz saatine güvenmeyen ikinci yol: belirteç beklenmedik
      // şekilde düştüyse bir kez yenileyip tekrar dene.
      await refresh();
      return _send(
        method,
        path,
        body: body,
        authenticated: authenticated,
        allowRefresh: false,
      );
    }

    if (response.statusCode >= 400) {
      throw ApiException.parse(
        response.statusCode,
        utf8.decode(response.bodyBytes),
      );
    }
    if (response.bodyBytes.isEmpty) return <String, dynamic>{};
    final decoded = jsonDecode(utf8.decode(response.bodyBytes));
    return decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
  }

  void close() => _client.close();
}
