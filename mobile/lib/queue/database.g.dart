// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'database.dart';

// ignore_for_file: type=lint
class $QueuedAnswersTable extends QueuedAnswers
    with TableInfo<$QueuedAnswersTable, QueuedAnswer> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $QueuedAnswersTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _answerIdMeta = const VerificationMeta(
    'answerId',
  );
  @override
  late final GeneratedColumn<String> answerId = GeneratedColumn<String>(
    'answer_id',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _runIdMeta = const VerificationMeta('runId');
  @override
  late final GeneratedColumn<String> runId = GeneratedColumn<String>(
    'run_id',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _itemIdMeta = const VerificationMeta('itemId');
  @override
  late final GeneratedColumn<String> itemId = GeneratedColumn<String>(
    'item_id',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _stateMeta = const VerificationMeta('state');
  @override
  late final GeneratedColumn<String> state = GeneratedColumn<String>(
    'state',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _valueJsonMeta = const VerificationMeta(
    'valueJson',
  );
  @override
  late final GeneratedColumn<String> valueJson = GeneratedColumn<String>(
    'value_json',
    aliasedName,
    true,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _noteMeta = const VerificationMeta('note');
  @override
  late final GeneratedColumn<String> note = GeneratedColumn<String>(
    'note',
    aliasedName,
    true,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _notDoneReasonMeta = const VerificationMeta(
    'notDoneReason',
  );
  @override
  late final GeneratedColumn<String> notDoneReason = GeneratedColumn<String>(
    'not_done_reason',
    aliasedName,
    true,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _answeredAtMeta = const VerificationMeta(
    'answeredAt',
  );
  @override
  late final GeneratedColumn<DateTime> answeredAt = GeneratedColumn<DateTime>(
    'answered_at',
    aliasedName,
    false,
    type: DriftSqlType.dateTime,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _deviceIdMeta = const VerificationMeta(
    'deviceId',
  );
  @override
  late final GeneratedColumn<String> deviceId = GeneratedColumn<String>(
    'device_id',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _sentMeta = const VerificationMeta('sent');
  @override
  late final GeneratedColumn<bool> sent = GeneratedColumn<bool>(
    'sent',
    aliasedName,
    false,
    type: DriftSqlType.bool,
    requiredDuringInsert: false,
    defaultConstraints: GeneratedColumn.constraintIsAlways(
      'CHECK ("sent" IN (0, 1))',
    ),
    defaultValue: const Constant(false),
  );
  static const VerificationMeta _lastErrorCodeMeta = const VerificationMeta(
    'lastErrorCode',
  );
  @override
  late final GeneratedColumn<String> lastErrorCode = GeneratedColumn<String>(
    'last_error_code',
    aliasedName,
    true,
    type: DriftSqlType.string,
    requiredDuringInsert: false,
  );
  static const VerificationMeta _blockedMeta = const VerificationMeta(
    'blocked',
  );
  @override
  late final GeneratedColumn<bool> blocked = GeneratedColumn<bool>(
    'blocked',
    aliasedName,
    false,
    type: DriftSqlType.bool,
    requiredDuringInsert: false,
    defaultConstraints: GeneratedColumn.constraintIsAlways(
      'CHECK ("blocked" IN (0, 1))',
    ),
    defaultValue: const Constant(false),
  );
  @override
  List<GeneratedColumn> get $columns => [
    answerId,
    runId,
    itemId,
    state,
    valueJson,
    note,
    notDoneReason,
    answeredAt,
    deviceId,
    sent,
    lastErrorCode,
    blocked,
  ];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'queued_answers';
  @override
  VerificationContext validateIntegrity(
    Insertable<QueuedAnswer> instance, {
    bool isInserting = false,
  }) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('answer_id')) {
      context.handle(
        _answerIdMeta,
        answerId.isAcceptableOrUnknown(data['answer_id']!, _answerIdMeta),
      );
    } else if (isInserting) {
      context.missing(_answerIdMeta);
    }
    if (data.containsKey('run_id')) {
      context.handle(
        _runIdMeta,
        runId.isAcceptableOrUnknown(data['run_id']!, _runIdMeta),
      );
    } else if (isInserting) {
      context.missing(_runIdMeta);
    }
    if (data.containsKey('item_id')) {
      context.handle(
        _itemIdMeta,
        itemId.isAcceptableOrUnknown(data['item_id']!, _itemIdMeta),
      );
    } else if (isInserting) {
      context.missing(_itemIdMeta);
    }
    if (data.containsKey('state')) {
      context.handle(
        _stateMeta,
        state.isAcceptableOrUnknown(data['state']!, _stateMeta),
      );
    } else if (isInserting) {
      context.missing(_stateMeta);
    }
    if (data.containsKey('value_json')) {
      context.handle(
        _valueJsonMeta,
        valueJson.isAcceptableOrUnknown(data['value_json']!, _valueJsonMeta),
      );
    }
    if (data.containsKey('note')) {
      context.handle(
        _noteMeta,
        note.isAcceptableOrUnknown(data['note']!, _noteMeta),
      );
    }
    if (data.containsKey('not_done_reason')) {
      context.handle(
        _notDoneReasonMeta,
        notDoneReason.isAcceptableOrUnknown(
          data['not_done_reason']!,
          _notDoneReasonMeta,
        ),
      );
    }
    if (data.containsKey('answered_at')) {
      context.handle(
        _answeredAtMeta,
        answeredAt.isAcceptableOrUnknown(data['answered_at']!, _answeredAtMeta),
      );
    } else if (isInserting) {
      context.missing(_answeredAtMeta);
    }
    if (data.containsKey('device_id')) {
      context.handle(
        _deviceIdMeta,
        deviceId.isAcceptableOrUnknown(data['device_id']!, _deviceIdMeta),
      );
    } else if (isInserting) {
      context.missing(_deviceIdMeta);
    }
    if (data.containsKey('sent')) {
      context.handle(
        _sentMeta,
        sent.isAcceptableOrUnknown(data['sent']!, _sentMeta),
      );
    }
    if (data.containsKey('last_error_code')) {
      context.handle(
        _lastErrorCodeMeta,
        lastErrorCode.isAcceptableOrUnknown(
          data['last_error_code']!,
          _lastErrorCodeMeta,
        ),
      );
    }
    if (data.containsKey('blocked')) {
      context.handle(
        _blockedMeta,
        blocked.isAcceptableOrUnknown(data['blocked']!, _blockedMeta),
      );
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {answerId};
  @override
  QueuedAnswer map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return QueuedAnswer(
      answerId: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}answer_id'],
      )!,
      runId: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}run_id'],
      )!,
      itemId: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}item_id'],
      )!,
      state: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}state'],
      )!,
      valueJson: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}value_json'],
      ),
      note: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}note'],
      ),
      notDoneReason: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}not_done_reason'],
      ),
      answeredAt: attachedDatabase.typeMapping.read(
        DriftSqlType.dateTime,
        data['${effectivePrefix}answered_at'],
      )!,
      deviceId: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}device_id'],
      )!,
      sent: attachedDatabase.typeMapping.read(
        DriftSqlType.bool,
        data['${effectivePrefix}sent'],
      )!,
      lastErrorCode: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}last_error_code'],
      ),
      blocked: attachedDatabase.typeMapping.read(
        DriftSqlType.bool,
        data['${effectivePrefix}blocked'],
      )!,
    );
  }

  @override
  $QueuedAnswersTable createAlias(String alias) {
    return $QueuedAnswersTable(attachedDatabase, alias);
  }
}

class QueuedAnswer extends DataClass implements Insertable<QueuedAnswer> {
  /// Cihazda üretilen UUID; sunucuya idempotency anahtarı olarak gider.
  final String answerId;
  final String runId;
  final String itemId;

  /// `passed` · `failed` · `not_done` · `not_applicable`
  final String state;

  /// Madde türüne göre değer, JSON olarak. Sayı, metin, seçim ve
  /// sıcaklık tek sütunda: tür bilgisi şablonda, burada taşımak onu
  /// ikinci kez saklamak olurdu.
  final String? valueJson;
  final String? note;
  final String? notDoneReason;

  /// Cihaz saatiyle cevap anı. Sunucu kendi saatini olay zamanı kabul
  /// ediyor; bu ham değer kayıtta kalıyor (BR-13).
  final DateTime answeredAt;
  final String deviceId;

  /// Sunucunun kabul ettiği ve artık gönderilmeyecek kayıt. Silinmek
  /// yerine işaretleniyor: gönderildiğini bilmek, ekranda "bekleyen"
  /// sayısını doğru göstermenin tek yolu.
  final bool sent;

  /// Son reddin makine kodu (`urn:` son parçası). Kullanıcıya metni
  /// ekran çeviriyor; burada kod duruyor.
  final String? lastErrorCode;

  /// Sunucu kalıcı olarak reddetti (`retryable: false`). Gönderilmedi
  /// ve **yeniden denenmeyecek**: her turda yeniden göndermek kuyruğu
  /// o kayıtla birlikte taşımak, yani tıkanmanın sessiz hâli olurdu.
  /// Kayıt silinmiyor; ekran bunu "kabul edilmedi" diye gösteriyor.
  final bool blocked;
  const QueuedAnswer({
    required this.answerId,
    required this.runId,
    required this.itemId,
    required this.state,
    this.valueJson,
    this.note,
    this.notDoneReason,
    required this.answeredAt,
    required this.deviceId,
    required this.sent,
    this.lastErrorCode,
    required this.blocked,
  });
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['answer_id'] = Variable<String>(answerId);
    map['run_id'] = Variable<String>(runId);
    map['item_id'] = Variable<String>(itemId);
    map['state'] = Variable<String>(state);
    if (!nullToAbsent || valueJson != null) {
      map['value_json'] = Variable<String>(valueJson);
    }
    if (!nullToAbsent || note != null) {
      map['note'] = Variable<String>(note);
    }
    if (!nullToAbsent || notDoneReason != null) {
      map['not_done_reason'] = Variable<String>(notDoneReason);
    }
    map['answered_at'] = Variable<DateTime>(answeredAt);
    map['device_id'] = Variable<String>(deviceId);
    map['sent'] = Variable<bool>(sent);
    if (!nullToAbsent || lastErrorCode != null) {
      map['last_error_code'] = Variable<String>(lastErrorCode);
    }
    map['blocked'] = Variable<bool>(blocked);
    return map;
  }

  QueuedAnswersCompanion toCompanion(bool nullToAbsent) {
    return QueuedAnswersCompanion(
      answerId: Value(answerId),
      runId: Value(runId),
      itemId: Value(itemId),
      state: Value(state),
      valueJson: valueJson == null && nullToAbsent
          ? const Value.absent()
          : Value(valueJson),
      note: note == null && nullToAbsent ? const Value.absent() : Value(note),
      notDoneReason: notDoneReason == null && nullToAbsent
          ? const Value.absent()
          : Value(notDoneReason),
      answeredAt: Value(answeredAt),
      deviceId: Value(deviceId),
      sent: Value(sent),
      lastErrorCode: lastErrorCode == null && nullToAbsent
          ? const Value.absent()
          : Value(lastErrorCode),
      blocked: Value(blocked),
    );
  }

  factory QueuedAnswer.fromJson(
    Map<String, dynamic> json, {
    ValueSerializer? serializer,
  }) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return QueuedAnswer(
      answerId: serializer.fromJson<String>(json['answerId']),
      runId: serializer.fromJson<String>(json['runId']),
      itemId: serializer.fromJson<String>(json['itemId']),
      state: serializer.fromJson<String>(json['state']),
      valueJson: serializer.fromJson<String?>(json['valueJson']),
      note: serializer.fromJson<String?>(json['note']),
      notDoneReason: serializer.fromJson<String?>(json['notDoneReason']),
      answeredAt: serializer.fromJson<DateTime>(json['answeredAt']),
      deviceId: serializer.fromJson<String>(json['deviceId']),
      sent: serializer.fromJson<bool>(json['sent']),
      lastErrorCode: serializer.fromJson<String?>(json['lastErrorCode']),
      blocked: serializer.fromJson<bool>(json['blocked']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'answerId': serializer.toJson<String>(answerId),
      'runId': serializer.toJson<String>(runId),
      'itemId': serializer.toJson<String>(itemId),
      'state': serializer.toJson<String>(state),
      'valueJson': serializer.toJson<String?>(valueJson),
      'note': serializer.toJson<String?>(note),
      'notDoneReason': serializer.toJson<String?>(notDoneReason),
      'answeredAt': serializer.toJson<DateTime>(answeredAt),
      'deviceId': serializer.toJson<String>(deviceId),
      'sent': serializer.toJson<bool>(sent),
      'lastErrorCode': serializer.toJson<String?>(lastErrorCode),
      'blocked': serializer.toJson<bool>(blocked),
    };
  }

  QueuedAnswer copyWith({
    String? answerId,
    String? runId,
    String? itemId,
    String? state,
    Value<String?> valueJson = const Value.absent(),
    Value<String?> note = const Value.absent(),
    Value<String?> notDoneReason = const Value.absent(),
    DateTime? answeredAt,
    String? deviceId,
    bool? sent,
    Value<String?> lastErrorCode = const Value.absent(),
    bool? blocked,
  }) => QueuedAnswer(
    answerId: answerId ?? this.answerId,
    runId: runId ?? this.runId,
    itemId: itemId ?? this.itemId,
    state: state ?? this.state,
    valueJson: valueJson.present ? valueJson.value : this.valueJson,
    note: note.present ? note.value : this.note,
    notDoneReason: notDoneReason.present
        ? notDoneReason.value
        : this.notDoneReason,
    answeredAt: answeredAt ?? this.answeredAt,
    deviceId: deviceId ?? this.deviceId,
    sent: sent ?? this.sent,
    lastErrorCode: lastErrorCode.present
        ? lastErrorCode.value
        : this.lastErrorCode,
    blocked: blocked ?? this.blocked,
  );
  QueuedAnswer copyWithCompanion(QueuedAnswersCompanion data) {
    return QueuedAnswer(
      answerId: data.answerId.present ? data.answerId.value : this.answerId,
      runId: data.runId.present ? data.runId.value : this.runId,
      itemId: data.itemId.present ? data.itemId.value : this.itemId,
      state: data.state.present ? data.state.value : this.state,
      valueJson: data.valueJson.present ? data.valueJson.value : this.valueJson,
      note: data.note.present ? data.note.value : this.note,
      notDoneReason: data.notDoneReason.present
          ? data.notDoneReason.value
          : this.notDoneReason,
      answeredAt: data.answeredAt.present
          ? data.answeredAt.value
          : this.answeredAt,
      deviceId: data.deviceId.present ? data.deviceId.value : this.deviceId,
      sent: data.sent.present ? data.sent.value : this.sent,
      lastErrorCode: data.lastErrorCode.present
          ? data.lastErrorCode.value
          : this.lastErrorCode,
      blocked: data.blocked.present ? data.blocked.value : this.blocked,
    );
  }

  @override
  String toString() {
    return (StringBuffer('QueuedAnswer(')
          ..write('answerId: $answerId, ')
          ..write('runId: $runId, ')
          ..write('itemId: $itemId, ')
          ..write('state: $state, ')
          ..write('valueJson: $valueJson, ')
          ..write('note: $note, ')
          ..write('notDoneReason: $notDoneReason, ')
          ..write('answeredAt: $answeredAt, ')
          ..write('deviceId: $deviceId, ')
          ..write('sent: $sent, ')
          ..write('lastErrorCode: $lastErrorCode, ')
          ..write('blocked: $blocked')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode => Object.hash(
    answerId,
    runId,
    itemId,
    state,
    valueJson,
    note,
    notDoneReason,
    answeredAt,
    deviceId,
    sent,
    lastErrorCode,
    blocked,
  );
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is QueuedAnswer &&
          other.answerId == this.answerId &&
          other.runId == this.runId &&
          other.itemId == this.itemId &&
          other.state == this.state &&
          other.valueJson == this.valueJson &&
          other.note == this.note &&
          other.notDoneReason == this.notDoneReason &&
          other.answeredAt == this.answeredAt &&
          other.deviceId == this.deviceId &&
          other.sent == this.sent &&
          other.lastErrorCode == this.lastErrorCode &&
          other.blocked == this.blocked);
}

class QueuedAnswersCompanion extends UpdateCompanion<QueuedAnswer> {
  final Value<String> answerId;
  final Value<String> runId;
  final Value<String> itemId;
  final Value<String> state;
  final Value<String?> valueJson;
  final Value<String?> note;
  final Value<String?> notDoneReason;
  final Value<DateTime> answeredAt;
  final Value<String> deviceId;
  final Value<bool> sent;
  final Value<String?> lastErrorCode;
  final Value<bool> blocked;
  final Value<int> rowid;
  const QueuedAnswersCompanion({
    this.answerId = const Value.absent(),
    this.runId = const Value.absent(),
    this.itemId = const Value.absent(),
    this.state = const Value.absent(),
    this.valueJson = const Value.absent(),
    this.note = const Value.absent(),
    this.notDoneReason = const Value.absent(),
    this.answeredAt = const Value.absent(),
    this.deviceId = const Value.absent(),
    this.sent = const Value.absent(),
    this.lastErrorCode = const Value.absent(),
    this.blocked = const Value.absent(),
    this.rowid = const Value.absent(),
  });
  QueuedAnswersCompanion.insert({
    required String answerId,
    required String runId,
    required String itemId,
    required String state,
    this.valueJson = const Value.absent(),
    this.note = const Value.absent(),
    this.notDoneReason = const Value.absent(),
    required DateTime answeredAt,
    required String deviceId,
    this.sent = const Value.absent(),
    this.lastErrorCode = const Value.absent(),
    this.blocked = const Value.absent(),
    this.rowid = const Value.absent(),
  }) : answerId = Value(answerId),
       runId = Value(runId),
       itemId = Value(itemId),
       state = Value(state),
       answeredAt = Value(answeredAt),
       deviceId = Value(deviceId);
  static Insertable<QueuedAnswer> custom({
    Expression<String>? answerId,
    Expression<String>? runId,
    Expression<String>? itemId,
    Expression<String>? state,
    Expression<String>? valueJson,
    Expression<String>? note,
    Expression<String>? notDoneReason,
    Expression<DateTime>? answeredAt,
    Expression<String>? deviceId,
    Expression<bool>? sent,
    Expression<String>? lastErrorCode,
    Expression<bool>? blocked,
    Expression<int>? rowid,
  }) {
    return RawValuesInsertable({
      if (answerId != null) 'answer_id': answerId,
      if (runId != null) 'run_id': runId,
      if (itemId != null) 'item_id': itemId,
      if (state != null) 'state': state,
      if (valueJson != null) 'value_json': valueJson,
      if (note != null) 'note': note,
      if (notDoneReason != null) 'not_done_reason': notDoneReason,
      if (answeredAt != null) 'answered_at': answeredAt,
      if (deviceId != null) 'device_id': deviceId,
      if (sent != null) 'sent': sent,
      if (lastErrorCode != null) 'last_error_code': lastErrorCode,
      if (blocked != null) 'blocked': blocked,
      if (rowid != null) 'rowid': rowid,
    });
  }

  QueuedAnswersCompanion copyWith({
    Value<String>? answerId,
    Value<String>? runId,
    Value<String>? itemId,
    Value<String>? state,
    Value<String?>? valueJson,
    Value<String?>? note,
    Value<String?>? notDoneReason,
    Value<DateTime>? answeredAt,
    Value<String>? deviceId,
    Value<bool>? sent,
    Value<String?>? lastErrorCode,
    Value<bool>? blocked,
    Value<int>? rowid,
  }) {
    return QueuedAnswersCompanion(
      answerId: answerId ?? this.answerId,
      runId: runId ?? this.runId,
      itemId: itemId ?? this.itemId,
      state: state ?? this.state,
      valueJson: valueJson ?? this.valueJson,
      note: note ?? this.note,
      notDoneReason: notDoneReason ?? this.notDoneReason,
      answeredAt: answeredAt ?? this.answeredAt,
      deviceId: deviceId ?? this.deviceId,
      sent: sent ?? this.sent,
      lastErrorCode: lastErrorCode ?? this.lastErrorCode,
      blocked: blocked ?? this.blocked,
      rowid: rowid ?? this.rowid,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (answerId.present) {
      map['answer_id'] = Variable<String>(answerId.value);
    }
    if (runId.present) {
      map['run_id'] = Variable<String>(runId.value);
    }
    if (itemId.present) {
      map['item_id'] = Variable<String>(itemId.value);
    }
    if (state.present) {
      map['state'] = Variable<String>(state.value);
    }
    if (valueJson.present) {
      map['value_json'] = Variable<String>(valueJson.value);
    }
    if (note.present) {
      map['note'] = Variable<String>(note.value);
    }
    if (notDoneReason.present) {
      map['not_done_reason'] = Variable<String>(notDoneReason.value);
    }
    if (answeredAt.present) {
      map['answered_at'] = Variable<DateTime>(answeredAt.value);
    }
    if (deviceId.present) {
      map['device_id'] = Variable<String>(deviceId.value);
    }
    if (sent.present) {
      map['sent'] = Variable<bool>(sent.value);
    }
    if (lastErrorCode.present) {
      map['last_error_code'] = Variable<String>(lastErrorCode.value);
    }
    if (blocked.present) {
      map['blocked'] = Variable<bool>(blocked.value);
    }
    if (rowid.present) {
      map['rowid'] = Variable<int>(rowid.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('QueuedAnswersCompanion(')
          ..write('answerId: $answerId, ')
          ..write('runId: $runId, ')
          ..write('itemId: $itemId, ')
          ..write('state: $state, ')
          ..write('valueJson: $valueJson, ')
          ..write('note: $note, ')
          ..write('notDoneReason: $notDoneReason, ')
          ..write('answeredAt: $answeredAt, ')
          ..write('deviceId: $deviceId, ')
          ..write('sent: $sent, ')
          ..write('lastErrorCode: $lastErrorCode, ')
          ..write('blocked: $blocked, ')
          ..write('rowid: $rowid')
          ..write(')'))
        .toString();
  }
}

class $CachedDocsTable extends CachedDocs
    with TableInfo<$CachedDocsTable, CachedDoc> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $CachedDocsTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _pathMeta = const VerificationMeta('path');
  @override
  late final GeneratedColumn<String> path = GeneratedColumn<String>(
    'path',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _bodyMeta = const VerificationMeta('body');
  @override
  late final GeneratedColumn<String> body = GeneratedColumn<String>(
    'body',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _fetchedAtMeta = const VerificationMeta(
    'fetchedAt',
  );
  @override
  late final GeneratedColumn<DateTime> fetchedAt = GeneratedColumn<DateTime>(
    'fetched_at',
    aliasedName,
    false,
    type: DriftSqlType.dateTime,
    requiredDuringInsert: true,
  );
  @override
  List<GeneratedColumn> get $columns => [path, body, fetchedAt];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'cached_docs';
  @override
  VerificationContext validateIntegrity(
    Insertable<CachedDoc> instance, {
    bool isInserting = false,
  }) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('path')) {
      context.handle(
        _pathMeta,
        path.isAcceptableOrUnknown(data['path']!, _pathMeta),
      );
    } else if (isInserting) {
      context.missing(_pathMeta);
    }
    if (data.containsKey('body')) {
      context.handle(
        _bodyMeta,
        body.isAcceptableOrUnknown(data['body']!, _bodyMeta),
      );
    } else if (isInserting) {
      context.missing(_bodyMeta);
    }
    if (data.containsKey('fetched_at')) {
      context.handle(
        _fetchedAtMeta,
        fetchedAt.isAcceptableOrUnknown(data['fetched_at']!, _fetchedAtMeta),
      );
    } else if (isInserting) {
      context.missing(_fetchedAtMeta);
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {path};
  @override
  CachedDoc map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return CachedDoc(
      path: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}path'],
      )!,
      body: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}body'],
      )!,
      fetchedAt: attachedDatabase.typeMapping.read(
        DriftSqlType.dateTime,
        data['${effectivePrefix}fetched_at'],
      )!,
    );
  }

  @override
  $CachedDocsTable createAlias(String alias) {
    return $CachedDocsTable(attachedDatabase, alias);
  }
}

class CachedDoc extends DataClass implements Insertable<CachedDoc> {
  /// İstek yolu (`/sync/manifest`, `/runs/<id>` …).
  final String path;
  final String body;
  final DateTime fetchedAt;
  const CachedDoc({
    required this.path,
    required this.body,
    required this.fetchedAt,
  });
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['path'] = Variable<String>(path);
    map['body'] = Variable<String>(body);
    map['fetched_at'] = Variable<DateTime>(fetchedAt);
    return map;
  }

  CachedDocsCompanion toCompanion(bool nullToAbsent) {
    return CachedDocsCompanion(
      path: Value(path),
      body: Value(body),
      fetchedAt: Value(fetchedAt),
    );
  }

  factory CachedDoc.fromJson(
    Map<String, dynamic> json, {
    ValueSerializer? serializer,
  }) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return CachedDoc(
      path: serializer.fromJson<String>(json['path']),
      body: serializer.fromJson<String>(json['body']),
      fetchedAt: serializer.fromJson<DateTime>(json['fetchedAt']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'path': serializer.toJson<String>(path),
      'body': serializer.toJson<String>(body),
      'fetchedAt': serializer.toJson<DateTime>(fetchedAt),
    };
  }

  CachedDoc copyWith({String? path, String? body, DateTime? fetchedAt}) =>
      CachedDoc(
        path: path ?? this.path,
        body: body ?? this.body,
        fetchedAt: fetchedAt ?? this.fetchedAt,
      );
  CachedDoc copyWithCompanion(CachedDocsCompanion data) {
    return CachedDoc(
      path: data.path.present ? data.path.value : this.path,
      body: data.body.present ? data.body.value : this.body,
      fetchedAt: data.fetchedAt.present ? data.fetchedAt.value : this.fetchedAt,
    );
  }

  @override
  String toString() {
    return (StringBuffer('CachedDoc(')
          ..write('path: $path, ')
          ..write('body: $body, ')
          ..write('fetchedAt: $fetchedAt')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode => Object.hash(path, body, fetchedAt);
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is CachedDoc &&
          other.path == this.path &&
          other.body == this.body &&
          other.fetchedAt == this.fetchedAt);
}

class CachedDocsCompanion extends UpdateCompanion<CachedDoc> {
  final Value<String> path;
  final Value<String> body;
  final Value<DateTime> fetchedAt;
  final Value<int> rowid;
  const CachedDocsCompanion({
    this.path = const Value.absent(),
    this.body = const Value.absent(),
    this.fetchedAt = const Value.absent(),
    this.rowid = const Value.absent(),
  });
  CachedDocsCompanion.insert({
    required String path,
    required String body,
    required DateTime fetchedAt,
    this.rowid = const Value.absent(),
  }) : path = Value(path),
       body = Value(body),
       fetchedAt = Value(fetchedAt);
  static Insertable<CachedDoc> custom({
    Expression<String>? path,
    Expression<String>? body,
    Expression<DateTime>? fetchedAt,
    Expression<int>? rowid,
  }) {
    return RawValuesInsertable({
      if (path != null) 'path': path,
      if (body != null) 'body': body,
      if (fetchedAt != null) 'fetched_at': fetchedAt,
      if (rowid != null) 'rowid': rowid,
    });
  }

  CachedDocsCompanion copyWith({
    Value<String>? path,
    Value<String>? body,
    Value<DateTime>? fetchedAt,
    Value<int>? rowid,
  }) {
    return CachedDocsCompanion(
      path: path ?? this.path,
      body: body ?? this.body,
      fetchedAt: fetchedAt ?? this.fetchedAt,
      rowid: rowid ?? this.rowid,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (path.present) {
      map['path'] = Variable<String>(path.value);
    }
    if (body.present) {
      map['body'] = Variable<String>(body.value);
    }
    if (fetchedAt.present) {
      map['fetched_at'] = Variable<DateTime>(fetchedAt.value);
    }
    if (rowid.present) {
      map['rowid'] = Variable<int>(rowid.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('CachedDocsCompanion(')
          ..write('path: $path, ')
          ..write('body: $body, ')
          ..write('fetchedAt: $fetchedAt, ')
          ..write('rowid: $rowid')
          ..write(')'))
        .toString();
  }
}

abstract class _$QueueDatabase extends GeneratedDatabase {
  _$QueueDatabase(QueryExecutor e) : super(e);
  $QueueDatabaseManager get managers => $QueueDatabaseManager(this);
  late final $QueuedAnswersTable queuedAnswers = $QueuedAnswersTable(this);
  late final $CachedDocsTable cachedDocs = $CachedDocsTable(this);
  @override
  Iterable<TableInfo<Table, Object?>> get allTables =>
      allSchemaEntities.whereType<TableInfo<Table, Object?>>();
  @override
  List<DatabaseSchemaEntity> get allSchemaEntities => [
    queuedAnswers,
    cachedDocs,
  ];
}

typedef $$QueuedAnswersTableCreateCompanionBuilder =
    QueuedAnswersCompanion Function({
      required String answerId,
      required String runId,
      required String itemId,
      required String state,
      Value<String?> valueJson,
      Value<String?> note,
      Value<String?> notDoneReason,
      required DateTime answeredAt,
      required String deviceId,
      Value<bool> sent,
      Value<String?> lastErrorCode,
      Value<bool> blocked,
      Value<int> rowid,
    });
typedef $$QueuedAnswersTableUpdateCompanionBuilder =
    QueuedAnswersCompanion Function({
      Value<String> answerId,
      Value<String> runId,
      Value<String> itemId,
      Value<String> state,
      Value<String?> valueJson,
      Value<String?> note,
      Value<String?> notDoneReason,
      Value<DateTime> answeredAt,
      Value<String> deviceId,
      Value<bool> sent,
      Value<String?> lastErrorCode,
      Value<bool> blocked,
      Value<int> rowid,
    });

class $$QueuedAnswersTableFilterComposer
    extends Composer<_$QueueDatabase, $QueuedAnswersTable> {
  $$QueuedAnswersTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<String> get answerId => $composableBuilder(
    column: $table.answerId,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get runId => $composableBuilder(
    column: $table.runId,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get itemId => $composableBuilder(
    column: $table.itemId,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get state => $composableBuilder(
    column: $table.state,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get valueJson => $composableBuilder(
    column: $table.valueJson,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get note => $composableBuilder(
    column: $table.note,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get notDoneReason => $composableBuilder(
    column: $table.notDoneReason,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<DateTime> get answeredAt => $composableBuilder(
    column: $table.answeredAt,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get deviceId => $composableBuilder(
    column: $table.deviceId,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<bool> get sent => $composableBuilder(
    column: $table.sent,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get lastErrorCode => $composableBuilder(
    column: $table.lastErrorCode,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<bool> get blocked => $composableBuilder(
    column: $table.blocked,
    builder: (column) => ColumnFilters(column),
  );
}

class $$QueuedAnswersTableOrderingComposer
    extends Composer<_$QueueDatabase, $QueuedAnswersTable> {
  $$QueuedAnswersTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<String> get answerId => $composableBuilder(
    column: $table.answerId,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get runId => $composableBuilder(
    column: $table.runId,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get itemId => $composableBuilder(
    column: $table.itemId,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get state => $composableBuilder(
    column: $table.state,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get valueJson => $composableBuilder(
    column: $table.valueJson,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get note => $composableBuilder(
    column: $table.note,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get notDoneReason => $composableBuilder(
    column: $table.notDoneReason,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<DateTime> get answeredAt => $composableBuilder(
    column: $table.answeredAt,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get deviceId => $composableBuilder(
    column: $table.deviceId,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<bool> get sent => $composableBuilder(
    column: $table.sent,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get lastErrorCode => $composableBuilder(
    column: $table.lastErrorCode,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<bool> get blocked => $composableBuilder(
    column: $table.blocked,
    builder: (column) => ColumnOrderings(column),
  );
}

class $$QueuedAnswersTableAnnotationComposer
    extends Composer<_$QueueDatabase, $QueuedAnswersTable> {
  $$QueuedAnswersTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<String> get answerId =>
      $composableBuilder(column: $table.answerId, builder: (column) => column);

  GeneratedColumn<String> get runId =>
      $composableBuilder(column: $table.runId, builder: (column) => column);

  GeneratedColumn<String> get itemId =>
      $composableBuilder(column: $table.itemId, builder: (column) => column);

  GeneratedColumn<String> get state =>
      $composableBuilder(column: $table.state, builder: (column) => column);

  GeneratedColumn<String> get valueJson =>
      $composableBuilder(column: $table.valueJson, builder: (column) => column);

  GeneratedColumn<String> get note =>
      $composableBuilder(column: $table.note, builder: (column) => column);

  GeneratedColumn<String> get notDoneReason => $composableBuilder(
    column: $table.notDoneReason,
    builder: (column) => column,
  );

  GeneratedColumn<DateTime> get answeredAt => $composableBuilder(
    column: $table.answeredAt,
    builder: (column) => column,
  );

  GeneratedColumn<String> get deviceId =>
      $composableBuilder(column: $table.deviceId, builder: (column) => column);

  GeneratedColumn<bool> get sent =>
      $composableBuilder(column: $table.sent, builder: (column) => column);

  GeneratedColumn<String> get lastErrorCode => $composableBuilder(
    column: $table.lastErrorCode,
    builder: (column) => column,
  );

  GeneratedColumn<bool> get blocked =>
      $composableBuilder(column: $table.blocked, builder: (column) => column);
}

class $$QueuedAnswersTableTableManager
    extends
        RootTableManager<
          _$QueueDatabase,
          $QueuedAnswersTable,
          QueuedAnswer,
          $$QueuedAnswersTableFilterComposer,
          $$QueuedAnswersTableOrderingComposer,
          $$QueuedAnswersTableAnnotationComposer,
          $$QueuedAnswersTableCreateCompanionBuilder,
          $$QueuedAnswersTableUpdateCompanionBuilder,
          (
            QueuedAnswer,
            BaseReferences<_$QueueDatabase, $QueuedAnswersTable, QueuedAnswer>,
          ),
          QueuedAnswer,
          PrefetchHooks Function()
        > {
  $$QueuedAnswersTableTableManager(
    _$QueueDatabase db,
    $QueuedAnswersTable table,
  ) : super(
        TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$QueuedAnswersTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$QueuedAnswersTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$QueuedAnswersTableAnnotationComposer($db: db, $table: table),
          updateCompanionCallback:
              ({
                Value<String> answerId = const Value.absent(),
                Value<String> runId = const Value.absent(),
                Value<String> itemId = const Value.absent(),
                Value<String> state = const Value.absent(),
                Value<String?> valueJson = const Value.absent(),
                Value<String?> note = const Value.absent(),
                Value<String?> notDoneReason = const Value.absent(),
                Value<DateTime> answeredAt = const Value.absent(),
                Value<String> deviceId = const Value.absent(),
                Value<bool> sent = const Value.absent(),
                Value<String?> lastErrorCode = const Value.absent(),
                Value<bool> blocked = const Value.absent(),
                Value<int> rowid = const Value.absent(),
              }) => QueuedAnswersCompanion(
                answerId: answerId,
                runId: runId,
                itemId: itemId,
                state: state,
                valueJson: valueJson,
                note: note,
                notDoneReason: notDoneReason,
                answeredAt: answeredAt,
                deviceId: deviceId,
                sent: sent,
                lastErrorCode: lastErrorCode,
                blocked: blocked,
                rowid: rowid,
              ),
          createCompanionCallback:
              ({
                required String answerId,
                required String runId,
                required String itemId,
                required String state,
                Value<String?> valueJson = const Value.absent(),
                Value<String?> note = const Value.absent(),
                Value<String?> notDoneReason = const Value.absent(),
                required DateTime answeredAt,
                required String deviceId,
                Value<bool> sent = const Value.absent(),
                Value<String?> lastErrorCode = const Value.absent(),
                Value<bool> blocked = const Value.absent(),
                Value<int> rowid = const Value.absent(),
              }) => QueuedAnswersCompanion.insert(
                answerId: answerId,
                runId: runId,
                itemId: itemId,
                state: state,
                valueJson: valueJson,
                note: note,
                notDoneReason: notDoneReason,
                answeredAt: answeredAt,
                deviceId: deviceId,
                sent: sent,
                lastErrorCode: lastErrorCode,
                blocked: blocked,
                rowid: rowid,
              ),
          withReferenceMapper: (p0) => p0
              .map(
                (e) => (
                  e.readTable<$QueuedAnswersTable, QueuedAnswer>(table),
                  BaseReferences<
                    _$QueueDatabase,
                    $QueuedAnswersTable,
                    QueuedAnswer
                  >(db, table, e),
                ),
              )
              .toList(),
          prefetchHooksCallback: null,
        ),
      );
}

typedef $$QueuedAnswersTableProcessedTableManager =
    ProcessedTableManager<
      _$QueueDatabase,
      $QueuedAnswersTable,
      QueuedAnswer,
      $$QueuedAnswersTableFilterComposer,
      $$QueuedAnswersTableOrderingComposer,
      $$QueuedAnswersTableAnnotationComposer,
      $$QueuedAnswersTableCreateCompanionBuilder,
      $$QueuedAnswersTableUpdateCompanionBuilder,
      (
        QueuedAnswer,
        BaseReferences<_$QueueDatabase, $QueuedAnswersTable, QueuedAnswer>,
      ),
      QueuedAnswer,
      PrefetchHooks Function()
    >;
typedef $$CachedDocsTableCreateCompanionBuilder = CachedDocsCompanion Function({
  required String path,
  required String body,
  required DateTime fetchedAt,
  Value<int> rowid,
});
typedef $$CachedDocsTableUpdateCompanionBuilder = CachedDocsCompanion Function({
  Value<String> path,
  Value<String> body,
  Value<DateTime> fetchedAt,
  Value<int> rowid,
});

class $$CachedDocsTableFilterComposer
    extends Composer<_$QueueDatabase, $CachedDocsTable> {
  $$CachedDocsTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<String> get path => $composableBuilder(
    column: $table.path,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get body => $composableBuilder(
    column: $table.body,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<DateTime> get fetchedAt => $composableBuilder(
    column: $table.fetchedAt,
    builder: (column) => ColumnFilters(column),
  );
}

class $$CachedDocsTableOrderingComposer
    extends Composer<_$QueueDatabase, $CachedDocsTable> {
  $$CachedDocsTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<String> get path => $composableBuilder(
    column: $table.path,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get body => $composableBuilder(
    column: $table.body,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<DateTime> get fetchedAt => $composableBuilder(
    column: $table.fetchedAt,
    builder: (column) => ColumnOrderings(column),
  );
}

class $$CachedDocsTableAnnotationComposer
    extends Composer<_$QueueDatabase, $CachedDocsTable> {
  $$CachedDocsTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<String> get path =>
      $composableBuilder(column: $table.path, builder: (column) => column);

  GeneratedColumn<String> get body =>
      $composableBuilder(column: $table.body, builder: (column) => column);

  GeneratedColumn<DateTime> get fetchedAt =>
      $composableBuilder(column: $table.fetchedAt, builder: (column) => column);
}

class $$CachedDocsTableTableManager
    extends
        RootTableManager<
          _$QueueDatabase,
          $CachedDocsTable,
          CachedDoc,
          $$CachedDocsTableFilterComposer,
          $$CachedDocsTableOrderingComposer,
          $$CachedDocsTableAnnotationComposer,
          $$CachedDocsTableCreateCompanionBuilder,
          $$CachedDocsTableUpdateCompanionBuilder,
          (
            CachedDoc,
            BaseReferences<_$QueueDatabase, $CachedDocsTable, CachedDoc>,
          ),
          CachedDoc,
          PrefetchHooks Function()
        > {
  $$CachedDocsTableTableManager(_$QueueDatabase db, $CachedDocsTable table)
    : super(
        TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$CachedDocsTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$CachedDocsTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$CachedDocsTableAnnotationComposer($db: db, $table: table),
          updateCompanionCallback:
              ({
                Value<String> path = const Value.absent(),
                Value<String> body = const Value.absent(),
                Value<DateTime> fetchedAt = const Value.absent(),
                Value<int> rowid = const Value.absent(),
              }) => CachedDocsCompanion(
                path: path,
                body: body,
                fetchedAt: fetchedAt,
                rowid: rowid,
              ),
          createCompanionCallback:
              ({
                required String path,
                required String body,
                required DateTime fetchedAt,
                Value<int> rowid = const Value.absent(),
              }) => CachedDocsCompanion.insert(
                path: path,
                body: body,
                fetchedAt: fetchedAt,
                rowid: rowid,
              ),
          withReferenceMapper: (p0) => p0
              .map(
                (e) => (
                  e.readTable<$CachedDocsTable, CachedDoc>(table),
                  BaseReferences<_$QueueDatabase, $CachedDocsTable, CachedDoc>(
                    db,
                    table,
                    e,
                  ),
                ),
              )
              .toList(),
          prefetchHooksCallback: null,
        ),
      );
}

typedef $$CachedDocsTableProcessedTableManager =
    ProcessedTableManager<
      _$QueueDatabase,
      $CachedDocsTable,
      CachedDoc,
      $$CachedDocsTableFilterComposer,
      $$CachedDocsTableOrderingComposer,
      $$CachedDocsTableAnnotationComposer,
      $$CachedDocsTableCreateCompanionBuilder,
      $$CachedDocsTableUpdateCompanionBuilder,
      (CachedDoc, BaseReferences<_$QueueDatabase, $CachedDocsTable, CachedDoc>),
      CachedDoc,
      PrefetchHooks Function()
    >;

class $QueueDatabaseManager {
  final _$QueueDatabase _db;
  $QueueDatabaseManager(this._db);
  $$QueuedAnswersTableTableManager get queuedAnswers =>
      $$QueuedAnswersTableTableManager(_db, _db.queuedAnswers);
  $$CachedDocsTableTableManager get cachedDocs =>
      $$CachedDocsTableTableManager(_db, _db.cachedDocs);
}
