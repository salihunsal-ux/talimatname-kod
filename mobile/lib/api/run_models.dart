/// Çalıştırma doldurma sözleşmesi: parti sonucu, görünüm, madde.
///
/// `models.dart` oturum ve manifesti taşıyor; doldurma akışı buraya
/// ayrıldı, yoksa tek dosya iki işin ortak çöplüğü olurdu.
library;

import 'dart:math';

import 'problem.dart';

/// Sözleşmenin varsayılan parti sınırı. Gerçeği manifest söylüyor
/// (`batch_answer_limit`); bu, manifest henüz indirilmemişken
/// kullanılan değer.
const defaultBatchAnswerLimit = 200;
const defaultBatchEvidenceLimit = 50;
const defaultMaxEvidencePerItem = 3;
const defaultQueueEvidenceLimit = 500;

/// Cihazda üretilen kayıt kimliği (RFC 4122 sürüm 4).
///
/// Paket eklemek yerine on satır: kimliğin tek işi çakışmamak ve
/// sunucuda idempotency anahtarı olmak.
String newAnswerId() {
  final rastgele = Random.secure();
  final baytlar = List<int>.generate(16, (_) => rastgele.nextInt(256));
  baytlar[6] = (baytlar[6] & 0x0f) | 0x40; // sürüm 4
  baytlar[8] = (baytlar[8] & 0x3f) | 0x80; // varyant 10xx
  final onalti = baytlar.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  return '${onalti.substring(0, 8)}-${onalti.substring(8, 12)}-'
      '${onalti.substring(12, 16)}-${onalti.substring(16, 20)}-'
      '${onalti.substring(20)}';
}

/// `/sync/batch` yanıtındaki tek kayıt.
///
/// Sonuç **kayıt başına**: tek bozuk kayıt yüzünden bütün isteğin
/// reddedilmesi, cihazın kuyruğunu sonsuza kadar tıkardı.
class BatchRow {
  const BatchRow({
    required this.answerId,
    required this.outcome,
    this.errorCode,
    this.retryable = false,
  });

  final String answerId;

  /// `accepted` · `duplicate` · `rejected`
  final String outcome;
  final String? errorCode;

  /// Sunucu bu kaydın **yeniden denenebileceğini** söylüyor mu. Kalıcı
  /// ret (pencere kapalı, geçersiz madde) yeniden gönderilirse kuyruk
  /// her turda aynı kaydı taşır: tıkanmanın sessiz hâli.
  final bool retryable;

  /// Çift kayıt da kabuldür: cihaz onu kuyruktan düşürebilmeli, yoksa
  /// yeniden gönderim sonsuza kadar sürer.
  bool get accepted => outcome == 'accepted' || outcome == 'duplicate';

  static BatchRow fromJson(Map<String, dynamic> json) {
    final hata = json['error'] as Map<String, dynamic>?;
    final tur = hata?['type'] as String?;
    return BatchRow(
      answerId: json['answer_id'] as String,
      outcome: json['outcome'] as String,
      errorCode: tur == null
          ? null
          : (tur.startsWith(urnPrefix) ? tur.substring(urnPrefix.length) : tur),
      retryable: (hata?['retryable'] ?? false) as bool,
    );
  }
}

/// `/sync/batch` yanıtındaki tek kanıt kaydı.
class EvidenceRow {
  const EvidenceRow({
    required this.evidenceId,
    required this.outcome,
    this.uploadUrl,
    this.errorCode,
    this.retryable = false,
  });

  final String evidenceId;

  /// `accepted` · `resumed` · `duplicate` · `rejected`
  final String outcome;

  /// Baytların yükleneceği adres. Yerel depoda **göreli**, nesne
  /// deposunda tam adres.
  final String? uploadUrl;
  final String? errorCode;
  final bool retryable;

  /// Yükleme bekleniyor: yeni kayıt ya da yarım kalmış yükleme.
  bool get needsUpload => outcome == 'accepted' || outcome == 'resumed';

  /// Aynı fotoğraf sunucuda zaten var; cihaz kuyruktan düşürebilir.
  bool get duplicate => outcome == 'duplicate';

  static EvidenceRow fromJson(Map<String, dynamic> json) {
    final hata = json['error'] as Map<String, dynamic>?;
    final tur = hata?['type'] as String?;
    return EvidenceRow(
      evidenceId: json['evidence_id'] as String,
      outcome: json['outcome'] as String,
      uploadUrl: json['upload_url'] as String?,
      errorCode: tur == null
          ? null
          : (tur.startsWith(urnPrefix) ? tur.substring(urnPrefix.length) : tur),
      retryable: (hata?['retryable'] ?? false) as bool,
    );
  }
}

class BatchResult {
  const BatchResult({required this.answers, this.evidence = const []});

  final List<BatchRow> answers;
  final List<EvidenceRow> evidence;

  static BatchResult fromJson(Map<String, dynamic> json) => BatchResult(
    answers: (json['answers'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(BatchRow.fromJson)
        .toList(growable: false),
    evidence: (json['evidence'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(EvidenceRow.fromJson)
        .toList(growable: false),
  );
}

/// Çalıştırma görünümü: bölümler, maddeler ve varsa sunucudaki cevap.
class RunView {
  const RunView({
    required this.runId,
    required this.templateName,
    required this.branchName,
    required this.status,
    required this.writableFrom,
    required this.toleranceEnd,
    required this.sections,
    required this.blockers,
    this.lockedByName,
    this.result,
    this.scorePercent,
  });

  final String runId;
  final String templateName;
  final String branchName;
  final String status;
  final DateTime writableFrom;
  final DateTime toleranceEnd;
  final List<RunSection> sections;

  /// Gönderimi engelleyen eksikler; **sunucu** hesaplıyor. Cihaz
  /// yeniden hesaplamıyor: iki yerde kural, iki kural demektir.
  final List<Blocker> blockers;

  /// Çalıştırmayı üstlenen kişi (FR-0521, çalıştırma kilidi).
  final String? lockedByName;

  /// Gönderilmiş çalıştırmada sonuç (`passed`/`failed`) ve puan.
  final String? result;
  final int? scorePercent;

  bool writableAt(DateTime now) =>
      !now.isBefore(writableFrom) && now.isBefore(toleranceEnd);

  List<RunItem> get answerableItems => [
    for (final bolum in sections)
      for (final madde in bolum.items)
        if (madde.answerable) madde,
  ];

  static RunView fromJson(Map<String, dynamic> json) => RunView(
    runId: json['run_id'] as String,
    templateName: (json['template_name'] ?? '') as String,
    branchName: (json['branch_name'] ?? '') as String,
    status: json['status'] as String,
    writableFrom: DateTime.parse(json['writable_from'] as String),
    toleranceEnd: DateTime.parse(json['tolerance_end'] as String),
    sections: (json['sections'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(RunSection.fromJson)
        .toList(growable: false),
    blockers: (json['blockers'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(
          (b) => Blocker(
            itemId: b['item_id'] as String,
            title: (b['title'] ?? '') as String,
            kind: (b['kind'] ?? '') as String,
          ),
        )
        .toList(growable: false),
    result: json['result'] as String?,
    scorePercent: (json['score_percent'] as num?)?.round(),
    lockedByName: json['locked_by_name'] as String?,
  );
}

/// Gönderimi engelleyen eksik. `kind`: `unanswered` · `evidence` · `note`.
class Blocker {
  const Blocker({
    required this.itemId,
    required this.title,
    required this.kind,
  });

  final String itemId;
  final String title;
  final String kind;
}

class RunSection {
  const RunSection({required this.title, required this.items});

  final String title;
  final List<RunItem> items;

  static RunSection fromJson(Map<String, dynamic> json) => RunSection(
    title: (json['title'] ?? '') as String,
    items: (json['items'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(RunItem.fromJson)
        .toList(growable: false),
  );
}

/// Çalıştırmadaki bir madde ve (varsa) sunucudaki cevabı.
///
/// Seçenekler burada **yok**: görünüm onları taşımıyor, şablon
/// sürümünden geliyor (`/template-versions/{id}`). Yayınlanmış sürüm
/// değişmediği için cihaz onu bir kez indirip saklar (BR-18).
class RunItem {
  const RunItem({
    required this.itemId,
    required this.title,
    required this.type,
    required this.typeLabel,
    required this.required,
    required this.photoRequired,
    required this.critical,
    this.minValue,
    this.maxValue,
    this.unit,
    this.serverState,
    this.serverNote,
    this.serverReason,
    this.serverEvidenceCount = 0,
  });

  final String itemId;
  final String title;
  final String type;
  final String typeLabel;
  final bool required;
  final bool photoRequired;
  final bool critical;
  final num? minValue;
  final num? maxValue;
  final String? unit;

  /// Sunucuda kayıtlı cevabın durumu; yoksa `null`.
  final String? serverState;
  final String? serverNote;
  final String? serverReason;

  /// Sunucuda bu cevaba bağlı kanıt sayısı (başka cihazdan da olabilir).
  final int serverEvidenceCount;

  bool get answerable => type != 'instruction';

  static RunItem fromJson(Map<String, dynamic> json) {
    final cevap = json['answer'] as Map<String, dynamic>?;
    return RunItem(
      itemId: json['item_id'] as String,
      title: (json['title'] ?? '') as String,
      type: json['type'] as String,
      typeLabel: (json['type_label'] ?? '') as String,
      required: (json['required'] ?? false) as bool,
      photoRequired: (json['photo_required'] ?? false) as bool,
      critical: (json['critical'] ?? false) as bool,
      minValue: json['min_value'] as num?,
      maxValue: json['max_value'] as num?,
      unit: json['unit'] as String?,
      serverState: cevap?['state'] as String?,
      serverNote: cevap?['note'] as String?,
      serverReason: cevap?['not_done_reason'] as String?,
      serverEvidenceCount: (cevap?['evidence_count'] as num?)?.toInt() ?? 0,
    );
  }
}

/// Seçim maddesinin bir şıkkı.
///
/// Sunucu şıkkı **etiketiyle** eşleştiriyor ve geçer/kalır kararını
/// `passing`den veriyor (`domain/answers.py`). Cihaz da aynısını
/// yapıyor; yoksa personel bastığı anda "Evet" görüp senkten sonra
/// "Başarısız"a dönen bir cevap görürdü.
class ChoiceOption {
  const ChoiceOption({required this.label, required this.passing});

  final String label;
  final bool passing;

  static ChoiceOption fromJson(Map<String, dynamic> json) => ChoiceOption(
    label: (json['label'] ?? '') as String,
    passing: (json['passing'] ?? true) as bool,
  );
}

/// Şablon sürümündeki madde tanımı; seçim maddesinin şıkları burada.
class VersionItem {
  const VersionItem({required this.itemId, required this.options, this.hint});

  final String itemId;
  final List<ChoiceOption> options;
  final String? hint;

  /// Sürüm gövdesini madde kimliğine göre haritalar.
  static Map<String, VersionItem> mapFromJson(Map<String, dynamic> json) {
    final sonuc = <String, VersionItem>{};
    for (final bolum in (json['sections'] as List<dynamic>? ?? const [])) {
      if (bolum is! Map<String, dynamic>) continue;
      for (final madde in (bolum['items'] as List<dynamic>? ?? const [])) {
        if (madde is! Map<String, dynamic>) continue;
        sonuc[madde['id'] as String] = VersionItem(
          itemId: madde['id'] as String,
          hint: madde['hint'] as String?,
          options: (madde['options'] as List<dynamic>? ?? const [])
              .whereType<Map<String, dynamic>>()
              .map(ChoiceOption.fromJson)
              .toList(growable: false),
        );
      }
    }
    return sonuc;
  }
}
