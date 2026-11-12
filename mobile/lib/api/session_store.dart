/// Oturumun cihazda saklanması.
///
/// Belirteç `flutter_secure_storage` ile. Sürüm 11'de Android
/// varsayılanı zaten şifreli: anahtar KeyStore'da RSA-OAEP ile
/// sarılıyor, veri AES-GCM ile yazılıyor (API 23+). Bu yüzden ayrıca
/// seçenek verilmiyor — verilen seçenek, varsayılanı zayıflatmadığını
/// her sürümde yeniden doğrulamak demek olurdu.
///
/// Web'de güvenli depo **yok**: tarayıcıda localStorage'a düşüyor. O
/// yüzden web yalnızca geliştirme döngüsü, dağıtılan hedef değil.
library;

import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'models.dart';

class SessionStore {
  SessionStore({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  static const _key = 'session';
  static const _deviceKey = 'device_id';

  final FlutterSecureStorage _storage;

  Future<Session?> read() async {
    final raw = await _storage.read(key: _key);
    if (raw == null) return null;
    try {
      return Session.fromStored(jsonDecode(raw) as Map<String, dynamic>);
    } on Object {
      // Biçim değiştiyse oturumu düşür: yarım okunmuş belirteçle
      // devam etmek, kullanıcıyı anlaşılmaz 401'lerle bırakır.
      await clear();
      return null;
    }
  }

  Future<void> write(Session session) =>
      _storage.write(key: _key, value: jsonEncode(session.toStored()));

  /// Oturum silinir ama **cihaz kimliği kalır**: çıkış yapmak cihazı
  /// değiştirmez ve kuyruktaki kayıtların sahibi aynı cihazdır.
  Future<void> clear() => _storage.delete(key: _key);

  Future<String?> readDeviceId() => _storage.read(key: _deviceKey);

  Future<void> writeDeviceId(String id) =>
      _storage.write(key: _deviceKey, value: id);
}
