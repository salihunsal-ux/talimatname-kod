/// Çevrimdışı kuyruğun kalıcı hâli (FR-0702, FR-0703).
///
/// Cevap **önce buraya** yazılır, sonra sunucuya gönderilir. Sıra
/// böyle: şubede bağlantı yok sayılır, varsa şans. Kayıt sunucu
/// "accepted" demeden silinmez.
///
/// Kimlik cihazda üretiliyor ve `(run, item)` için **sabit**: aynı
/// maddeyi çevrimdışıyken üç kez değiştiren personel sunucuda üç satır
/// değil, bir satır oluşturur (TC-053).
library;

import 'package:drift/drift.dart';
import 'package:drift_flutter/drift_flutter.dart';

part 'database.g.dart';

/// Gönderilmeyi bekleyen cevap.
class QueuedAnswers extends Table {
  /// Cihazda üretilen UUID; sunucuya idempotency anahtarı olarak gider.
  TextColumn get answerId => text()();

  TextColumn get runId => text()();
  TextColumn get itemId => text()();

  /// `passed` · `failed` · `not_done` · `not_applicable`
  TextColumn get state => text()();

  /// Madde türüne göre değer, JSON olarak. Sayı, metin, seçim ve
  /// sıcaklık tek sütunda: tür bilgisi şablonda, burada taşımak onu
  /// ikinci kez saklamak olurdu.
  TextColumn get valueJson => text().nullable()();

  TextColumn get note => text().nullable()();
  TextColumn get notDoneReason => text().nullable()();

  /// Cihaz saatiyle cevap anı. Sunucu kendi saatini olay zamanı kabul
  /// ediyor; bu ham değer kayıtta kalıyor (BR-13).
  DateTimeColumn get answeredAt => dateTime()();

  TextColumn get deviceId => text()();

  /// Sunucunun kabul ettiği ve artık gönderilmeyecek kayıt. Silinmek
  /// yerine işaretleniyor: gönderildiğini bilmek, ekranda "bekleyen"
  /// sayısını doğru göstermenin tek yolu.
  BoolColumn get sent => boolean().withDefault(const Constant(false))();

  /// Son reddin makine kodu (`urn:` son parçası). Kullanıcıya metni
  /// ekran çeviriyor; burada kod duruyor.
  TextColumn get lastErrorCode => text().nullable()();

  /// Sunucu kalıcı olarak reddetti (`retryable: false`). Gönderilmedi
  /// ve **yeniden denenmeyecek**: her turda yeniden göndermek kuyruğu
  /// o kayıtla birlikte taşımak, yani tıkanmanın sessiz hâli olurdu.
  /// Kayıt silinmiyor; ekran bunu "kabul edilmedi" diye gösteriyor.
  BoolColumn get blocked => boolean().withDefault(const Constant(false))();

  @override
  Set<Column> get primaryKey => {answerId};
}

@DriftDatabase(tables: [QueuedAnswers])
class QueueDatabase extends _$QueueDatabase {
  QueueDatabase([QueryExecutor? executor])
    : super(
        executor ??
            driftDatabase(
              name: 'talimatname_kuyruk',
              // Web'de sqlite WASM olarak yükleniyor ve bu iki dosya
              // `web/` altında duruyor. Verilmezse veritabanı **hiç
              // açılmıyor**; tarayıcıda denerken tam bu oldu ve hata
              // sessizce yutulduğu için ekran "hepsi gönderildi"
              // diyordu. Web yalnızca geliştirme hedefi, ama sessiz
              // kuyruk en kötü hata türü.
              web: DriftWebOptions(
                sqlite3Wasm: Uri.parse('sqlite3.wasm'),
                driftWorker: Uri.parse('drift_worker.js'),
              ),
            ),
      );

  @override
  int get schemaVersion => 1;

  /// `(run, item)` için var olan kayıt; yoksa `null`.
  Future<QueuedAnswer?> forItem(String runId, String itemId) =>
      (select(queuedAnswers)
            ..where((t) => t.runId.equals(runId) & t.itemId.equals(itemId)))
          .getSingleOrNull();

  Future<void> put(QueuedAnswersCompanion row) =>
      into(queuedAnswers).insertOnConflictUpdate(row);

  Future<List<QueuedAnswer>> pending({int? limit}) {
    final q = select(queuedAnswers)
      ..where((t) => t.sent.equals(false) & t.blocked.equals(false))
      ..orderBy([(t) => OrderingTerm(expression: t.answeredAt)]);
    if (limit != null) q.limit(limit);
    return q.get();
  }

  Future<List<QueuedAnswer>> forRun(String runId) =>
      (select(queuedAnswers)..where((t) => t.runId.equals(runId))).get();

  Future<void> markSent(Iterable<String> answerIds) =>
      (update(queuedAnswers)..where((t) => t.answerId.isIn(answerIds))).write(
        const QueuedAnswersCompanion(
          sent: Value(true),
          lastErrorCode: Value(null),
        ),
      );

  Future<void> markRejected(
    String answerId,
    String code, {
    required bool permanent,
  }) =>
      (update(queuedAnswers)..where((t) => t.answerId.equals(answerId))).write(
        QueuedAnswersCompanion(
          lastErrorCode: Value(code),
          blocked: Value(permanent),
        ),
      );

  /// Gönderilmiş kayıtları temizler. Kuyruk sınırsız büyümemeli ama
  /// temizlik **gönderim onayından sonra** olur.
  Future<int> purgeSent() =>
      (delete(queuedAnswers)..where((t) => t.sent.equals(true))).go();

  Future<int> pendingCount() async => (await pending()).length;
}
