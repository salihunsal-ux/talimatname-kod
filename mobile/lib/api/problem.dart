/// RFC 9457 `application/problem+json` (ADR-0014 md.8).
///
/// İstemci **`type`'a göre** davranır, metne göre değil: `title`
/// Türkçe ve değişebilir, `type` sözleşmedir. Bu yüzden `title`
/// doğrudan ekrana basılmaz — `type` bilinen bir koda eşlenir, bilinmeyen
/// kodda genel metin gösterilir.
library;

import 'dart:convert';

const urnPrefix = 'urn:talimatname:';

/// Sunucunun verdiği alan hatası (doğrulama).
class FieldError {
  const FieldError({required this.field, required this.reason});

  final String field;
  final String reason;

  static FieldError fromJson(Map<String, dynamic> json) => FieldError(
    field: (json['alan'] ?? json['field'] ?? '') as String,
    reason: (json['sebep'] ?? json['reason'] ?? '') as String,
  );
}

class ApiException implements Exception {
  ApiException({
    required this.statusCode,
    required this.type,
    this.title,
    this.detail,
    this.fieldErrors = const [],
    this.retryable = false,
  });

  /// Ağ katmanı hatası: istek sunucuya hiç varmadı.
  factory ApiException.network(Object cause) => ApiException(
    statusCode: 0,
    type: '${urnPrefix}aglanamadi',
    detail: cause.toString(),
    retryable: true,
  );

  final int statusCode;

  /// Tam URN (`urn:talimatname:pencere-kapali`).
  final String type;
  final String? title;
  final String? detail;
  final List<FieldError> fieldErrors;
  final bool retryable;

  /// URN'in son parçası; kodda karşılaştırmak için.
  String get code =>
      type.startsWith(urnPrefix) ? type.substring(urnPrefix.length) : type;

  bool get isUnauthorized => statusCode == 401 || statusCode == 403;
  bool get isNetwork => statusCode == 0;

  static ApiException parse(int statusCode, String body) {
    Map<String, dynamic> json;
    try {
      final decoded = jsonDecode(body);
      json = decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
    } on FormatException {
      // Gövde problem+json değil (vekil sunucu hatası, HTML sayfası).
      json = <String, dynamic>{};
    }
    final errors = json['errors'];
    return ApiException(
      statusCode: statusCode,
      type: (json['type'] ?? '${urnPrefix}bilinmeyen') as String,
      title: json['title'] as String?,
      detail: json['detail'] as String?,
      fieldErrors: errors is List
          ? errors
                .whereType<Map<String, dynamic>>()
                .map(FieldError.fromJson)
                .toList(growable: false)
          : const [],
      // 5xx ve 429 tekrar denenebilir; 4xx'in kalanı cihazın hatası.
      retryable: statusCode >= 500 || statusCode == 429,
    );
  }

  @override
  String toString() => 'ApiException($statusCode, $type)';
}
