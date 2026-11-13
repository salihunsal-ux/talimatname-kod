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

/// Sunucudan en son alınan belgeler (manifest, çalıştırma görünümü,
/// şablon sürümü). Şubede bağlantı yokken uygulama açılırsa liste
/// buradan gelir; emülatörde görüldü ki bu olmadan kuyruk ve oturum
/// dursa da ekran boş kalıyor ve personel iş göremiyor (FR-0701).
class CachedDocs extends Table {
  /// İstek yolu (`/sync/manifest`, `/runs/<id>` …).
  TextColumn get path => text()();
  TextColumn get body => text()();
  DateTimeColumn get fetchedAt => dateTime()();

  @override
  Set<Column> get primaryKey => {path};
}

/// Gönderilmeyi bekleyen kanıt fotoğrafı (FR-0601…0606).
///
/// Baytlar veritabanında değil **dosyada**; satır dosyanın yolunu ve
/// özetini taşıyor. Özet çekim anında hesaplanıyor ve sunucu yüklemeden
/// sonra aynı özeti kendi hesaplıyor: yolda değişen dosya reddedilir.
class QueuedEvidence extends Table {
  TextColumn get evidenceId => text()();
  TextColumn get runId => text()();
  TextColumn get itemId => text()();

  /// Kanıtın bağlandığı cevap; sunucu cevabı görmeden kanıtı kabul
  /// etmez, bu yüzden kanıt cevaptan **sonra** gönderilir.
  TextColumn get answerId => text()();
  TextColumn get filePath => text()();
  TextColumn get sha256 => text()();
  IntColumn get sizeBytes => integer()();
  TextColumn get contentType => text()();
  DateTimeColumn get capturedAt => dateTime()();
  TextColumn get deviceId => text()();

  /// Çekim anındaki konum; alınamadıysa boş (izin yok, GPS kapalı).
  RealColumn get latitude => real().nullable()();
  RealColumn get longitude => real().nullable()();

  /// Baytlar yüklendi ve sunucu özeti doğruladı.
  BoolColumn get uploaded => boolean().withDefault(const Constant(false))();
  BoolColumn get blocked => boolean().withDefault(const Constant(false))();
  TextColumn get lastErrorCode => text().nullable()();

  @override
  Set<Column> get primaryKey => {evidenceId};
}

@DriftDatabase(tables: [QueuedAnswers, CachedDocs, QueuedEvidence])
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
  int get schemaVersion => 4;

  @override
  MigrationStrategy get migration => MigrationStrategy(
    onCreate: (m) => m.createAll(),
    onUpgrade: (m, from, to) async {
      // 1 → 2: belge önbelleği eklendi. Kuyruk tablosuna dokunulmuyor:
      // yükseltme, gönderilmemiş cevabı silemez.
      if (from < 2) await m.createTable(cachedDocs);
      // 2 → 3: kanıt kuyruğu.
      if (from < 3) {
        await m.createTable(queuedEvidence);
      } else if (from < 4) {
        // 3 → 4: kanıta konum. Tablo 3'te kurulduysa sütun eklenir;
        // daha eskiden gelen kurulum tabloyu zaten yeni hâliyle kurdu.
        await m.addColumn(queuedEvidence, queuedEvidence.latitude);
        await m.addColumn(queuedEvidence, queuedEvidence.longitude);
      }
    },
  );

  Future<void> putDoc(String path, String body) => into(cachedDocs)
      .insertOnConflictUpdate(
        CachedDocsCompanion.insert(
          path: path,
          body: body,
          fetchedAt: DateTime.now(),
        ),
      );

  Future<CachedDoc?> getDoc(String path) =>
      (select(cachedDocs)..where((t) => t.path.equals(path))).getSingleOrNull();

  /// Oturum kapanınca önbellek silinir: başka biri giriş yaparsa
  /// öncekinin listelerini görmemeli.
  Future<int> clearDocs() => delete(cachedDocs).go();

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

  /// Bekleyen **her şey**: cevaplar ve yüklenmemiş fotoğraflar. Sayaç
  /// yalnızca cevapları sayarsa, fotoğrafı yüklenmemiş bir liste
  /// "hepsi gönderildi" görünür.
  Future<int> pendingCount() async =>
      (await pending()).length + (await pendingEvidence()).length;

  Future<void> putEvidence(QueuedEvidenceCompanion row) =>
      into(queuedEvidence).insertOnConflictUpdate(row);

  Future<List<QueuedEvidenceData>> evidenceForRun(String runId) =>
      (select(queuedEvidence)..where((t) => t.runId.equals(runId))).get();

  /// Maddeye bağlı, reddedilmemiş kanıt sayısı (yüklenmiş olanlar dahil).
  Future<int> evidenceCount(String runId, String itemId) async =>
      (await (select(queuedEvidence)..where(
                (t) =>
                    t.runId.equals(runId) &
                    t.itemId.equals(itemId) &
                    t.blocked.equals(false),
              ))
              .get())
          .length;

  Future<List<QueuedEvidenceData>> pendingEvidence({int? limit}) {
    final q = select(queuedEvidence)
      ..where((t) => t.uploaded.equals(false) & t.blocked.equals(false))
      ..orderBy([(t) => OrderingTerm(expression: t.capturedAt)]);
    if (limit != null) q.limit(limit);
    return q.get();
  }

  Future<void> markEvidenceUploaded(String evidenceId) =>
      (update(
        queuedEvidence,
      )..where((t) => t.evidenceId.equals(evidenceId))).write(
        const QueuedEvidenceCompanion(
          uploaded: Value(true),
          lastErrorCode: Value(null),
        ),
      );

  Future<void> markEvidenceRejected(
    String evidenceId,
    String code, {
    required bool permanent,
  }) => (update(queuedEvidence)..where((t) => t.evidenceId.equals(evidenceId)))
      .write(
        QueuedEvidenceCompanion(
          lastErrorCode: Value(code),
          blocked: Value(permanent),
        ),
      );

  Future<QueuedEvidenceData?> evidenceById(String evidenceId) => (select(
    queuedEvidence,
  )..where((t) => t.evidenceId.equals(evidenceId))).getSingleOrNull();

  Future<int> deleteEvidence(String evidenceId) => (delete(
    queuedEvidence,
  )..where((t) => t.evidenceId.equals(evidenceId))).go();

  Future<List<String>> sentAnswerIds() async => [
    for (final c in await (select(
      queuedAnswers,
    )..where((t) => t.sent.equals(true))).get())
      c.answerId,
  ];

  /// Cevabı yeniden gönderilecek diye işaretler (kanıt sayısı değişti).
  Future<void> markUnsent(String answerId) =>
      (update(queuedAnswers)..where((t) => t.answerId.equals(answerId))).write(
        const QueuedAnswersCompanion(sent: Value(false)),
      );
}
