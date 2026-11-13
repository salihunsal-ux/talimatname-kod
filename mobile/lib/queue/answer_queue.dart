/// Kuyruk ile sunucu arasındaki tek kapı.
///
/// Ekran buraya "şu maddeyi şöyle cevapladım" der; gönderim, dilimleme
/// ve sonucun yorumlanması burada olur. Spike A'nın sunucu yarısı bu
/// sözleşmeyi ölçtü (`api/tests/test_spike_a_senk.py`); buradaki iş,
/// istemcinin o sözleşmeye uymasını sağlamak.
library;

import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

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
    this.uploaded = 0,
    this.remaining = 0,
    this.failure,
  });

  final int accepted;
  final int rejected;

  /// Baytları yüklenip sunucuda doğrulanan fotoğraf sayısı.
  final int uploaded;

  /// Turdan sonra kuyrukta kalan gönderilmemiş kayıt.
  final int remaining;

  /// Tur hiç tamamlanamadıysa sebebi (ağ yok, oturum düştü). Kayıtlar
  /// kuyrukta durur.
  final ApiException? failure;

  bool get ok => failure == null;
}

class AnswerQueue {
  AnswerQueue({
    required this.db,
    required this.api,
    required this.deviceId,
    this.evidenceDir,
  });

  /// Fotoğraf dosyalarının durduğu dizin. `null` ise kanıt eklenemez
  /// (web hedefi).
  final Directory? evidenceDir;

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

  /// Çekilmiş fotoğrafı kuyruğa ekler.
  ///
  /// Sınırlar **cihazda** uygulanıyor, çünkü sunucu kuyruk sınırını
  /// yalnızca yayınlıyor, zorlamıyor (Spike A bulgusu, TC-054): madde
  /// başına en çok `maxEvidencePerItem`, kuyrukta en çok
  /// `queueEvidenceLimit` yüklenmemiş fotoğraf.
  Future<PhotoResult> addPhoto({
    required String runId,
    required String itemId,
    required List<int> bytes,
    String contentType = 'image/jpeg',
    QueuePolicy? policy,
    DateTime? at,
  }) async {
    final dizin = evidenceDir;
    if (dizin == null) return PhotoResult.unsupported;
    final cevap = await db.forItem(runId, itemId);
    // Kanıt bir cevaba bağlanır; cevapsız maddeye fotoğraf eklenemez.
    if (cevap == null) return PhotoResult.needsAnswer;

    final maddeSiniri = policy?.maxEvidencePerItem ?? defaultMaxEvidencePerItem;
    if (await db.evidenceCount(runId, itemId) >= maddeSiniri) {
      return PhotoResult.itemFull;
    }
    final kuyrukSiniri =
        policy?.queueEvidenceLimit ?? defaultQueueEvidenceLimit;
    if ((await db.pendingEvidence()).length >= kuyrukSiniri) {
      return PhotoResult.queueFull;
    }

    final kimlik = newAnswerId();
    final uzanti = contentType == 'image/png' ? 'png' : 'jpg';
    await dizin.create(recursive: true);
    final dosya = File('${dizin.path}${Platform.pathSeparator}$kimlik.$uzanti');
    await dosya.writeAsBytes(bytes, flush: true);

    await db.putEvidence(
      QueuedEvidenceCompanion.insert(
        evidenceId: kimlik,
        runId: runId,
        itemId: itemId,
        answerId: cevap.answerId,
        filePath: dosya.path,
        sha256: sha256.convert(bytes).toString(),
        sizeBytes: bytes.length,
        contentType: contentType,
        capturedAt: at ?? DateTime.now(),
        deviceId: deviceId,
      ),
    );
    // Cevap kanıt sayısını beyan ediyor; sayı değişti, yeniden gitmeli.
    await db.markUnsent(cevap.answerId);
    return PhotoResult.added;
  }

  /// Cihazdan çıkmamış fotoğrafı kaldırır.
  ///
  /// Yüklenmiş kanıt **kaldırılamaz**: sunucuya ulaşan kanıt
  /// değiştirilemez kayıttır ve sunucuda silme ucu yok (FR-0609). O
  /// durumda `false` döner ve hiçbir şey değişmez.
  Future<bool> removePhoto(String evidenceId) async {
    final kayit = await db.evidenceById(evidenceId);
    if (kayit == null || kayit.uploaded) return false;
    await db.deleteEvidence(evidenceId);
    final dosya = File(kayit.filePath);
    if (dosya.existsSync()) await dosya.delete();
    // Cevabın beyan ettiği kanıt sayısı değişti.
    await db.markUnsent(kayit.answerId);
    return true;
  }

  Future<List<QueuedEvidenceData>> evidenceForRun(String runId) =>
      db.evidenceForRun(runId);

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
        result = await api.syncAnswers([
          for (final row in batch)
            _toWire(row, await db.evidenceCount(row.runId, row.itemId)),
        ]);
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

    // Kanıtlar cevaplardan **sonra**: sunucu cevabı görmeden kanıtı
    // kabul etmez.
    var uploaded = 0;
    final kanitSiniri = policy?.batchEvidenceLimit ?? defaultBatchEvidenceLimit;
    while (true) {
      final gonderilmis = {for (final c in await db.sentAnswerIds()) c};
      final batch = [
        for (final k in await db.pendingEvidence())
          if (gonderilmis.contains(k.answerId)) k,
      ].take(kanitSiniri).toList();
      if (batch.isEmpty) break;

      var ilerleme = false;
      try {
        final result = await api.syncEvidence(
          batch.map(_evidenceWire).toList(),
        );
        final satirlar = {for (final k in batch) k.evidenceId: k};
        for (final row in result.evidence) {
          final kayit = satirlar[row.evidenceId];
          if (kayit == null) continue;
          if (row.duplicate) {
            await _evidenceDone(kayit);
            ilerleme = true;
          } else if (row.needsUpload && row.uploadUrl != null) {
            final dosya = File(kayit.filePath);
            if (!dosya.existsSync()) {
              // Dosya yok: yüklenemez. Sessizce atlamak yerine kalıcı
              // ret olarak işaretle; ekran bunu gösterir.
              await db.markEvidenceRejected(
                kayit.evidenceId,
                'dosya-yok',
                permanent: true,
              );
              rejected++;
              ilerleme = true;
              continue;
            }
            await api.uploadEvidence(
              row.uploadUrl!,
              await dosya.readAsBytes(),
              kayit.contentType,
            );
            await api.completeEvidence(kayit.evidenceId);
            await _evidenceDone(kayit);
            uploaded++;
            ilerleme = true;
          } else {
            rejected++;
            await db.markEvidenceRejected(
              kayit.evidenceId,
              row.errorCode ?? 'bilinmeyen',
              permanent: !row.retryable,
            );
            if (!row.retryable) ilerleme = true;
          }
        }
      } on ApiException catch (hata) {
        return SyncOutcome(
          accepted: accepted,
          rejected: rejected,
          uploaded: uploaded,
          remaining: await db.pendingCount(),
          failure: hata,
        );
      }
      if (!ilerleme) break;
    }

    return SyncOutcome(
      accepted: accepted,
      rejected: rejected,
      uploaded: uploaded,
      remaining: await db.pendingCount(),
    );
  }

  /// Yüklenen fotoğrafın yerel kopyası silinir: sunucuda duruyor ve
  /// cihazın deposu sınırlı. Satır kalır; madde başına sayı ondan.
  Future<void> _evidenceDone(QueuedEvidenceData kayit) async {
    await db.markEvidenceUploaded(kayit.evidenceId);
    final dosya = File(kayit.filePath);
    if (dosya.existsSync()) await dosya.delete();
  }

  Map<String, dynamic> _evidenceWire(QueuedEvidenceData k) => {
    'evidence_id': k.evidenceId,
    'run_id': k.runId,
    'answer_id': k.answerId,
    'item_id': k.itemId,
    'sha256': k.sha256,
    'content_type': k.contentType,
    'size_bytes': k.sizeBytes,
    // Galeri yolu uygulamada yok; her kanıt kameradan (FR-0602).
    'from_gallery': false,
    'captured_at': k.capturedAt.toUtc().toIso8601String(),
    'device_id': k.deviceId,
  };

  Map<String, dynamic> _toWire(QueuedAnswer row, int evidenceCount) => {
    'answer_id': row.answerId,
    'run_id': row.runId,
    'item_id': row.itemId,
    'state': row.state,
    if (row.valueJson != null) 'value': jsonDecode(row.valueJson!),
    if (row.note != null) 'note': row.note,
    if (row.notDoneReason != null) 'not_done_reason': row.notDoneReason,
    'device_id': row.deviceId,
    'answered_at': row.answeredAt.toUtc().toIso8601String(),
    'evidence_count': evidenceCount,
  };
}

/// Fotoğraf ekleme denemesinin sonucu.
enum PhotoResult {
  added,

  /// Madde henüz cevaplanmadı.
  needsAnswer,

  /// Madde başına sınır doldu.
  itemFull,

  /// Cihaz kuyruğu doldu; bağlantı gelip fotoğraflar yüklenmeden yenisi
  /// çekilemez (TC-054).
  queueFull,

  /// Bu hedefte fotoğraf yok (web).
  unsupported,
}
