/// Ağ varsa sunucudan, yoksa cihazdaki son kopyadan.
///
/// Kural basit ve bilerek dar: **yalnızca ağ hatasında** önbelleğe
/// düşülür. Sunucu "hayır" dediyse (403, 404, 409) o cevap geçerlidir;
/// eski kopyayı göstermek, kullanıcıya artık doğru olmayan bir listeyi
/// doğruymuş gibi sunmak olurdu.
library;

import 'dart:convert';

import '../api/api_client.dart';
import '../api/problem.dart';
import 'database.dart';

/// Bir belge ve nereden geldiği.
class Doc {
  const Doc({required this.json, required this.fetchedAt, required this.stale});

  final Map<String, dynamic> json;
  final DateTime fetchedAt;

  /// Sunucuya ulaşılamadı; bu, cihazdaki son kopya.
  final bool stale;
}

class DocCache {
  DocCache({required this.db, required this.api});

  final QueueDatabase db;
  final ApiClient api;

  /// Belge önbellekte yoksa (ya da [maxAge]'den eskiyse) indirir.
  /// İndirdiyse `true`. [maxAge] verilmezse var olan kopya yeterlidir:
  /// değişmeyen belgeler (yayınlanmış şablon sürümü) için.
  Future<bool> warm(String path, {Duration? maxAge}) async {
    final kayit = await db.getDoc(path);
    if (kayit != null) {
      if (maxAge == null) return false;
      if (DateTime.now().difference(kayit.fetchedAt) < maxAge) return false;
    }
    final json = await api.getJson(path);
    await db.putDoc(path, jsonEncode(json));
    return true;
  }

  Future<Doc> get(String path) async {
    try {
      final json = await api.getJson(path);
      await db.putDoc(path, jsonEncode(json));
      return Doc(json: json, fetchedAt: DateTime.now(), stale: false);
    } on ApiException catch (hata) {
      if (!hata.isNetwork) rethrow;
      final kayit = await db.getDoc(path);
      if (kayit == null) rethrow;
      return Doc(
        json: jsonDecode(kayit.body) as Map<String, dynamic>,
        fetchedAt: kayit.fetchedAt,
        stale: true,
      );
    }
  }
}
