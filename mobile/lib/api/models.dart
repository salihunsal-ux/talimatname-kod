/// Sunucu sözleşmesinin cihaz tarafındaki karşılığı.
///
/// Elle yazıldı. 02-repo "üretilmiş API istemcisi" diyor ve doğrusu o;
/// ilk dikey dilim için üç uç nokta elle yazıldı, üreteç (openapi →
/// dart) sonraki iş. Depo arayüzü (`ApiClient`) aynı kaldığı için
/// üretece geçmek çağrı yerlerini değiştirmiyor.
library;

/// `POST /auth/verify` ve `/auth/refresh` yanıtı.
///
/// Sunucu süreyi **dakika olarak** veriyor (`expires_in_minutes`), an
/// olarak değil; son kullanma anı cihazda hesaplanıyor. Cihaz saati
/// yanlışsa bu an da yanlış olur — o yüzden yenileme kararı yalnızca
/// bunun üzerine kurulmuyor: 401 gelirse de bir kez yenilenip istek
/// tekrarlanıyor (bkz. `ApiClient`).
class Session {
  const Session({
    required this.accessToken,
    required this.expiresAt,
    required this.refreshToken,
    required this.refreshExpiresAt,
    required this.fullName,
    required this.roles,
  });

  final String accessToken;
  final DateTime expiresAt;
  final String refreshToken;
  final DateTime refreshExpiresAt;
  final String fullName;

  /// Rol kodları (`staff`, `branch_manager`, …). Etiketi sunucu da
  /// veriyor ama ekranda rol gösterilmiyor; kod yetki kararı için.
  final List<String> roles;

  /// Süre dolmasına 60 saniye kalınca yenile: ağ gecikmesi payı.
  bool get needsRefresh => DateTime.now().toUtc().isAfter(
    expiresAt.toUtc().subtract(const Duration(seconds: 60)),
  );

  bool get refreshUsable =>
      DateTime.now().toUtc().isBefore(refreshExpiresAt.toUtc());

  static Session fromJson(Map<String, dynamic> json, {DateTime? now}) {
    final user = json['user'] as Map<String, dynamic>? ?? const {};
    final roles = user['roles'];
    final minutes = (json['expires_in_minutes'] as num).toInt();
    return Session(
      accessToken: json['access_token'] as String,
      expiresAt: (now ?? DateTime.now()).toUtc().add(
        Duration(minutes: minutes),
      ),
      refreshToken: json['refresh_token'] as String,
      refreshExpiresAt: DateTime.parse(json['refresh_expires_at'] as String),
      fullName: (user['full_name'] ?? '') as String,
      roles: roles is List
          ? roles
                .whereType<Map<String, dynamic>>()
                .map((r) => (r['role'] ?? '').toString())
                .where((r) => r.isNotEmpty)
                .toList(growable: false)
          : const [],
    );
  }

  /// Cihazda saklanan şekil. Sunucunun yanıtı değil: `expires_at` an
  /// olarak yazılıyor, çünkü uygulama kapanıp açıldığında kalan dakika
  /// bilgisi anlamsız olur.
  Map<String, dynamic> toStored() => {
    'access_token': accessToken,
    'expires_at': expiresAt.toUtc().toIso8601String(),
    'refresh_token': refreshToken,
    'refresh_expires_at': refreshExpiresAt.toUtc().toIso8601String(),
    'full_name': fullName,
    'roles': roles,
  };

  static Session fromStored(Map<String, dynamic> json) => Session(
    accessToken: json['access_token'] as String,
    expiresAt: DateTime.parse(json['expires_at'] as String),
    refreshToken: json['refresh_token'] as String,
    refreshExpiresAt: DateTime.parse(json['refresh_expires_at'] as String),
    fullName: (json['full_name'] ?? '') as String,
    roles: (json['roles'] as List<dynamic>? ?? const [])
        .map((r) => r.toString())
        .toList(growable: false),
  );
}

/// Cihazın uygulayacağı sınırlar. Kuyruk sınırı ile **parti** sınırı
/// ayrı: parti aşılırsa sunucu bütün isteği reddeder (Spike A bulgusu),
/// bu yüzden cihaz kuyruğunu `batch*Limit`e göre dilimler.
class QueuePolicy {
  const QueuePolicy({
    required this.maxEvidencePerItem,
    required this.maxEvidenceBytes,
    required this.queueEvidenceLimit,
    required this.queueHours,
    required this.batchAnswerLimit,
    required this.batchEvidenceLimit,
  });

  final int maxEvidencePerItem;
  final int maxEvidenceBytes;
  final int queueEvidenceLimit;
  final int queueHours;
  final int batchAnswerLimit;
  final int batchEvidenceLimit;

  static QueuePolicy fromJson(Map<String, dynamic> json) => QueuePolicy(
    maxEvidencePerItem: json['max_evidence_per_item'] as int,
    maxEvidenceBytes: json['max_evidence_bytes'] as int,
    queueEvidenceLimit: json['queue_evidence_limit'] as int,
    queueHours: json['queue_hours'] as int,
    batchAnswerLimit: json['batch_answer_limit'] as int,
    batchEvidenceLimit: json['batch_evidence_limit'] as int,
  );
}

/// Manifestteki bir çalıştırma. Alan adı `run_id` (`id` değil).
class ManifestRun {
  const ManifestRun({
    required this.runId,
    required this.planName,
    required this.branchName,
    required this.templateVersionId,
    required this.businessDay,
    required this.status,
    required this.windowStart,
    required this.windowEnd,
    required this.toleranceEnd,
    required this.writableFrom,
  });

  final String runId;
  final String planName;
  final String branchName;
  final String templateVersionId;
  final String businessDay;
  final String status;
  final DateTime windowStart;
  final DateTime windowEnd;
  final DateTime toleranceEnd;

  /// Yazmanın açıldığı an (BR-02a hazırlık payı). Cihaz bundan önce
  /// doldurmaya davet etmez; sunucu `pencere-acilmadi` ile reddeder.
  final DateTime writableFrom;

  bool writableAt(DateTime now) =>
      !now.isBefore(writableFrom) && now.isBefore(toleranceEnd);

  bool openedBy(DateTime now) => !now.isBefore(writableFrom);

  static ManifestRun fromJson(Map<String, dynamic> json) => ManifestRun(
    runId: json['run_id'] as String,
    planName: json['plan_name'] as String,
    branchName: json['branch_name'] as String,
    templateVersionId: json['template_version_id'] as String,
    businessDay: json['business_day'] as String,
    status: json['status'] as String,
    windowStart: DateTime.parse(json['window_start'] as String),
    windowEnd: DateTime.parse(json['window_end'] as String),
    toleranceEnd: DateTime.parse(json['tolerance_end'] as String),
    writableFrom: DateTime.parse(json['writable_from'] as String),
  );
}

/// `GET /sync/manifest`. Şablon sürümleri yalnızca **kimlik** taşır;
/// içerik `GET /template-versions/{id}` ile alınır ve yayınlanmış sürüm
/// değişmediği için süresiz önbelleğe alınabilir (BR-18).
class Manifest {
  const Manifest({
    required this.serverTime,
    required this.skewMinutes,
    required this.skewFlagged,
    required this.horizonHours,
    required this.refreshAfterMinutes,
    required this.runs,
    required this.policy,
    this.notDoneReasons = const [],
  });

  final DateTime serverTime;
  final int? skewMinutes;
  final bool skewFlagged;
  final int horizonHours;
  final int refreshAfterMinutes;
  final List<ManifestRun> runs;
  final QueuePolicy policy;

  /// "Yapılamadı" sebepleri; etiketleri sunucu veriyor (BR-09).
  final List<NotDoneReason> notDoneReasons;

  static Manifest fromJson(Map<String, dynamic> json) {
    final clock = json['clock'] as Map<String, dynamic>;
    final runs = json['runs'] as List<dynamic>;
    return Manifest(
      serverTime: DateTime.parse(clock['server_time'] as String),
      skewMinutes: clock['skew_minutes'] as int?,
      skewFlagged: (clock['flagged'] ?? false) as bool,
      horizonHours: json['horizon_hours'] as int,
      refreshAfterMinutes: json['refresh_after_minutes'] as int,
      runs: runs
          .whereType<Map<String, dynamic>>()
          .map(ManifestRun.fromJson)
          .toList(growable: false),
      policy: QueuePolicy.fromJson(json['policy'] as Map<String, dynamic>),
      notDoneReasons: (json['not_done_reasons'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(
            (s) => NotDoneReason(
              code: s['code'] as String,
              label: s['label'] as String,
            ),
          )
          .toList(growable: false),
    );
  }
}

class NotDoneReason {
  const NotDoneReason({required this.code, required this.label});

  final String code;
  final String label;
}
