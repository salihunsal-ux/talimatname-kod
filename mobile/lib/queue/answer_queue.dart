/// Kuyruk ile sunucu arasındaki tek kapı.
///
/// Ekran buraya "şu maddeyi şöyle cevapladım" der; gönderim, dilimleme
/// ve sonucun yorumlanması burada olur. Spike A'nın sunucu yarısı bu
/// sözleşmeyi ölçtü (`api/tests/test_spike_a_senk.py`); buradaki iş,
/// istemcinin o sözleşmeye uymasını sağlamak.
library;

import 'dart:convert';

import 'package:drift/drift.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../api/run_models.dart';
import '../api/problem.dart';
import 'database.dart';

/// Bir senk turunun sonucu.
class SyncOutcome {
  const SyncOutcome({
    this.accepted = 0,
    this.rejected = 0,
    this.remaining = 0,
    this.failure,
  });

  final int accepted;
  final int rejected;

  /// Turdan sonra kuyrukta kalan gönderilmemiş kayıt.
  final int remaining;

  /// Tur hiç tamamlanamadıysa sebebi (ağ yok, oturum düştü). Kayıtlar
  /// kuyrukta durur.
  final ApiException? failure;

  bool get ok => failure == null;
}

class AnswerQueue {
  AnswerQueue({required this.db, required this.api, required this.deviceId});

  final QueueDatabase db;
  final ApiClient api;

  /// Cihaz kimliği kurulumda üretilip saklanıyor; kayıtla birlikte
  /// gidiyor ki aynı çalıştırmayı iki cihaz doldurduğunda hangisinin
  /// yazdığı belli olsun.
  final String deviceId;

  /// Cevabı kuyruğa yazar ve **kayıt kimliğini** döndürür.
  ///
  /// Kimlik `(run, item)` için sabit: aynı madde yeniden
  /// cevaplandığında var olan satır güncelleniyor, yenisi açılmıyor.
  /// Gönderilmiş bir cevabın değişmesi `sent`i sıfırlıyor — değişiklik
  /// de gönderilmeli.
  Future<String> answer({
    required String runId,
    required String itemId,
    required String state,
    Object? value,
    String? note,
    String? notDoneReason,
    DateTime? at,
  }) async {
    final existing = await db.forItem(runId, itemId);
    final answerId = existing?.answerId ?? newAnswerId();
    await db.put(
      QueuedAnswersCompanion.insert(
        answerId: answerId,
        runId: runId,
        itemId: itemId,
        state: state,
        valueJson: Value(value == null ? null : jsonEncode(value)),
        note: Value(note),
        notDoneReason: Value(notDoneReason),
        answeredAt: at ?? DateTime.now(),
        deviceId: deviceId,
        sent: const Value(false),
        lastErrorCode: const Value(null),
      ),
    );
    return answerId;
  }

  Future<List<QueuedAnswer>> forRun(String runId) => db.forRun(runId);

  Future<int> pendingCount() => db.pendingCount();

  /// Bekleyen kayıtları sunucuya gönderir.
  ///
  /// Parti sınırı **manifestten** geliyor (`batch_answer_limit`):
  /// aşılırsa sunucu tek tek değil **bütün isteği** reddediyor, yani
  /// kuyruk sonsuza kadar tıkanırdı. Sınır bilinmiyorsa sözleşmenin
  /// varsayılanı kullanılıyor.
  Future<SyncOutcome> sync({QueuePolicy? policy}) async {
    final limit = policy?.batchAnswerLimit ?? defaultBatchAnswerLimit;
    var accepted = 0;
    var rejected = 0;

    while (true) {
      final batch = await db.pending(limit: limit);
      if (batch.isEmpty) break;

      final BatchResult result;
      try {
        result = await api.syncAnswers(batch.map(_toWire).toList());
      } on ApiException catch (hata) {
        return SyncOutcome(
          accepted: accepted,
          rejected: rejected,
          remaining: await db.pendingCount(),
          failure: hata,
        );
      }

      final ok = <String>[];
      var ilerleme = false;
      for (final row in result.answers) {
        if (row.accepted) {
          ok.add(row.answerId);
          accepted++;
          ilerleme = true;
          continue;
        }
        rejected++;
        // Kalıcı ret kuyruktan **çıkarılıyor** (silinmeden): yeniden
        // göndermek her turda aynı kaydı taşımak olurdu.
        await db.markRejected(
          row.answerId,
          row.errorCode ?? 'bilinmeyen',
          permanent: !row.retryable,
        );
        if (!row.retryable) ilerleme = true;
      }
      await db.markSent(ok);

      // Hiçbir kayıt ilerlemediyse dur: aynı partiyi sonsuza kadar
      // göndermek, kuyruğu tıkamanın diğer adı.
      if (!ilerleme) break;
    }

    return SyncOutcome(
      accepted: accepted,
      rejected: rejected,
      remaining: await db.pendingCount(),
    );
  }

  Map<String, dynamic> _toWire(QueuedAnswer row) => {
    'answer_id': row.answerId,
    'run_id': row.runId,
    'item_id': row.itemId,
    'state': row.state,
    if (row.valueJson != null) 'value': jsonDecode(row.valueJson!),
    if (row.note != null) 'note': row.note,
    if (row.notDoneReason != null) 'not_done_reason': row.notDoneReason,
    'device_id': row.deviceId,
    'answered_at': row.answeredAt.toUtc().toIso8601String(),
  };
}
