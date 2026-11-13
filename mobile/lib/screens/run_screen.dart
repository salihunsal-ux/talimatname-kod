/// Liste doldurma ekranı.
///
/// Cevap **önce kuyruğa** yazılır, sonra gönderilir: şubede bağlantı
/// yok sayılır. Ekranda görünen durum kuyruktan gelir, sunucudan değil
/// — personel yazdığı şeyi anında görmeli, ağın dönmesini beklememeli.
///
/// Bu sürümde fotoğraf yok (Spike C): fotoğraf isteyen madde
/// işaretleniyor ve gönderimi sunucu zaten engelliyor.
library;

import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../api/models.dart';
import '../api/problem.dart';
import '../api/run_models.dart';
import '../l10n/strings.dart';
import '../queue/database.dart';
import '../state/providers.dart';
import '../state/run_providers.dart';
import '../theme/tokens.dart';
import '../widgets/error_text.dart';

class RunScreen extends ConsumerWidget {
  const RunScreen({required this.runId, super.key});

  final String runId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = AppColors.of(context);
    final detay = ref.watch(runDetailProvider(runId));

    return Scaffold(
      appBar: AppBar(
        backgroundColor: c.anchor,
        foregroundColor: c.anchorInk,
        title: Text(
          detay.value?.view.templateName ?? S.appTitle,
          style: const TextStyle(
            fontSize: TypeScale.sectionTitle,
            fontWeight: FontWeight.w600,
          ),
        ),
        actions: const [PendingBadge()],
      ),
      body: detay.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (hata, _) => Padding(
          padding: const EdgeInsets.all(Gap.x4),
          child: ErrorText(
            error: hata is ApiException
                ? hata
                : ApiException(statusCode: 0, type: '${urnPrefix}bilinmeyen'),
          ),
        ),
        data: (detay) => _Body(detay: detay),
      ),
    );
  }
}

class _Body extends ConsumerWidget {
  const _Body({required this.detay});

  final RunDetail detay;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Gönderilmiş ya da kapanmış çalıştırma salt okunur: pencere açık
    // olsa da sunucu yazmayı reddeder.
    final acik =
        detay.view.status == 'scheduled' || detay.view.status == 'in_progress';
    final yazilabilir = acik && detay.view.writableAt(DateTime.now());
    final ben = ref.watch(sessionProvider).value?.fullName;
    // Kuyruk ayrı sağlayıcıdan: cevap yazınca yalnızca bu tazeleniyor,
    // görünüm için ağa gidilmiyor.
    final kuyruk = {
      for (final satir
          in ref.watch(queuedForRunProvider(detay.view.runId)).value ??
              const <QueuedAnswer>[])
        satir.itemId: satir,
    };

    final sebepler =
        ref.watch(manifestProvider).value?.notDoneReasons ??
        const <NotDoneReason>[];

    return ListView(
      padding: const EdgeInsets.all(Gap.x4),
      children: [
        if (detay.staleSince != null)
          _notice(context, S.offlineSince(_hhmm(detay.staleSince!))),
        if (detay.view.status == 'submitted')
          _notice(context, S.alreadySubmitted)
        else if (!yazilabilir)
          _notice(context, S.readOnlyWindow),
        // Listeyi üstlenen kişiye kendi adını söylemenin anlamı yok.
        if (detay.view.lockedByName != null && detay.view.lockedByName != ben)
          _notice(context, S.lockedBy(detay.view.lockedByName!)),
        for (final bolum in detay.view.sections) ...[
          Padding(
            padding: const EdgeInsets.only(top: Gap.x4, bottom: Gap.x2),
            child: Text(
              bolum.title,
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          for (final madde in bolum.items)
            Padding(
              padding: const EdgeInsets.only(bottom: Gap.x3),
              child: _ItemCard(
                runId: detay.view.runId,
                item: madde,
                // Anahtar maddeye bağlı: not yazarken kart yeniden
                // kurulmamalı, yoksa yazılan metin kaybolur.
                key: ValueKey(madde.itemId),
                options: detay.options[madde.itemId]?.options ?? const [],
                reasons: sebepler,
                queued: kuyruk[madde.itemId],
                enabled: yazilabilir,
              ),
            ),
        ],
        const SizedBox(height: Gap.x4),
        _SubmitBar(view: detay.view, enabled: yazilabilir),
        const SizedBox(height: Gap.x8),
      ],
    );
  }

  static String _hhmm(DateTime t) =>
      '${t.hour.toString().padLeft(2, '0')}:'
      '${t.minute.toString().padLeft(2, '0')}';

  Widget _notice(BuildContext context, String text) {
    final c = AppColors.of(context);
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: Gap.x3),
      padding: const EdgeInsets.all(Gap.x3),
      decoration: BoxDecoration(
        color: c.warningLight,
        borderRadius: BorderRadius.circular(Corner.button),
      ),
      child: Text(
        text,
        style: TextStyle(color: c.warning, fontSize: TypeScale.label),
      ),
    );
  }
}

/// Tek madde: başlık, tür bilgisi, cevap denetimi ve gerekiyorsa
/// sebep + not.
///
/// Sunucunun iki kuralı burada karşılanıyor; yoksa kayıt ya senkte
/// reddedilir ya da liste gönderilemez:
///
/// * "Yapılamadı" **sebepsiz yazılamaz** (BR-09). Bu yüzden düğmeye
///   basmak cevabı yazmıyor; önce sebep seçtiriyor.
/// * Başarısız ve yapılamadı cevaplarında **not zorunlu** (BR-06).
class _ItemCard extends ConsumerStatefulWidget {
  const _ItemCard({
    required this.runId,
    required this.item,
    required this.options,
    required this.reasons,
    required this.queued,
    required this.enabled,
    super.key,
  });

  final String runId;
  final RunItem item;
  final List<ChoiceOption> options;
  final List<NotDoneReason> reasons;
  final QueuedAnswer? queued;
  final bool enabled;

  @override
  ConsumerState<_ItemCard> createState() => _ItemCardState();
}

class _ItemCardState extends ConsumerState<_ItemCard> {
  /// "Yapılamadı"ya basıldı ama sebep henüz seçilmedi.
  bool _awaitingReason = false;

  late final TextEditingController _note = TextEditingController(
    text: widget.queued?.note ?? widget.item.serverNote ?? '',
  );

  RunItem get item => widget.item;
  QueuedAnswer? get queued => widget.queued;

  String? get _state => queued?.state ?? item.serverState;
  String? get _reason => queued?.notDoneReason ?? item.serverReason;

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  void _write(
    String state, {
    Object? value,
    String? reason,
    bool keepValue = false,
  }) {
    final eskiDeger = queued?.valueJson == null
        ? null
        : jsonDecode(queued!.valueJson!);
    final not = _note.text.trim();
    ref
        .read(answerProvider)(
          runId: widget.runId,
          itemId: item.itemId,
          state: state,
          value: keepValue ? eskiDeger : value,
          note: not.isEmpty ? null : not,
          notDoneReason: state == 'not_done' ? reason : null,
        )
        .ignore();
  }

  /// Not değiştiyse cevabı aynı durum ve değerle yeniden yazar.
  void _saveNote() {
    final durum = _state;
    if (durum == null) return;
    final yeni = _note.text.trim();
    final eski = (queued?.note ?? item.serverNote ?? '').trim();
    if (yeni == eski) return;
    _write(durum, reason: _reason, keepValue: true);
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    if (!item.answerable) {
      // Talimat maddesi puanlanmıyor ve cevaplanmıyor; okunacak metin.
      return Container(
        padding: const EdgeInsets.all(Gap.x4),
        decoration: BoxDecoration(
          color: c.surface2,
          borderRadius: BorderRadius.circular(Corner.card),
        ),
        child: Text(item.title, style: Theme.of(context).textTheme.bodyLarge),
      );
    }

    final durum = _state;
    final sorunlu = durum == 'failed' || durum == 'not_done';
    return Container(
      padding: const EdgeInsets.all(Gap.x4),
      decoration: BoxDecoration(
        color: c.surface,
        border: Border.all(color: durum == null ? c.line : c.brand),
        borderRadius: BorderRadius.circular(Corner.card),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  item.title,
                  style: Theme.of(context).textTheme.bodyLarge,
                ),
              ),
              if (item.critical)
                _chip(context, S.criticalItem, c.critical, c.criticalLight),
            ],
          ),
          if (item.photoRequired || sorunlu) ...[
            const SizedBox(height: Gap.x2),
            // Fotoğraf yolu Spike C'de. Gizlemek yerine söylüyoruz:
            // personel listeyi neden gönderemediğini bilmeli.
            Text(
              sorunlu ? S.photoNeededForIssue : S.photoNotYet,
              style: TextStyle(color: c.warning, fontSize: TypeScale.meta),
            ),
          ],
          const SizedBox(height: Gap.x3),
          _control(context),
          if (_awaitingReason || durum == 'not_done') ...[
            const SizedBox(height: Gap.x3),
            Text(
              S.reasonTitle,
              style: TextStyle(color: c.ink2, fontSize: TypeScale.label),
            ),
            const SizedBox(height: Gap.x2),
            Wrap(
              spacing: Gap.x2,
              runSpacing: Gap.x2,
              children: [
                for (final sebep in widget.reasons)
                  SizedBox(
                    width: 150,
                    child: _Pick(
                      label: sebep.label,
                      color: c.warning,
                      selected: !_awaitingReason && _reason == sebep.code,
                      enabled: widget.enabled,
                      onTap: () {
                        setState(() => _awaitingReason = false);
                        _write('not_done', reason: sebep.code);
                      },
                    ),
                  ),
              ],
            ),
          ],
          if (sorunlu && !_awaitingReason) ...[
            const SizedBox(height: Gap.x3),
            TextField(
              controller: _note,
              enabled: widget.enabled,
              minLines: 1,
              maxLines: 3,
              decoration: const InputDecoration(labelText: S.noteLabel),
              onSubmitted: (_) => _saveNote(),
              onTapOutside: (_) {
                FocusScope.of(context).unfocus();
                _saveNote();
              },
            ),
          ],
          if (queued != null && !queued!.sent) ...[
            const SizedBox(height: Gap.x2),
            Text(
              queued!.lastErrorCode == null ? S.pendingOne : S.rejectedOne,
              style: TextStyle(
                color: queued!.lastErrorCode == null ? c.muted : c.critical,
                fontSize: TypeScale.meta,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _control(BuildContext context) {
    switch (item.type) {
      case 'choice':
        return _Choices(
          options: widget.options,
          selected: queued?.valueJson,
          enabled: widget.enabled,
          // Geçer/kalır kararını şıkkın kendisi taşıyor; sunucu da
          // aynı kuralı uyguluyor, yani ekranda görünen sonuç senkten
          // sonra değişmiyor.
          onPick: (secim) =>
              _write(secim.passing ? 'passed' : 'failed', value: secim.label),
        );
      case 'number':
      case 'temperature':
        return _NumberField(
          item: item,
          initial: queued?.valueJson,
          enabled: widget.enabled,
          onSubmit: (sayi, aralikta) =>
              _write(aralikta ? 'passed' : 'failed', value: sayi),
        );
      case 'text':
        return _TextField(
          initial: queued?.valueJson,
          enabled: widget.enabled,
          onSubmit: (metin) => _write('passed', value: metin),
        );
      default:
        return _YesNo(
          state: _awaitingReason ? 'not_done' : _state,
          enabled: widget.enabled,
          onPick: (yeni) {
            if (yeni == 'not_done') {
              // Sebepsiz "yapılamadı" sunucuda reddedilir; cevap sebep
              // seçilince yazılır.
              setState(() => _awaitingReason = true);
              return;
            }
            setState(() => _awaitingReason = false);
            _write(yeni);
          },
        );
    }
  }

  Widget _chip(BuildContext context, String text, Color fg, Color bg) =>
      Container(
        padding: const EdgeInsets.symmetric(
          horizontal: Gap.x3,
          vertical: Gap.x1,
        ),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(Corner.chip),
        ),
        child: Text(
          text,
          style: TextStyle(
            color: fg,
            fontSize: TypeScale.meta,
            fontWeight: FontWeight.w600,
          ),
        ),
      );
}

/// Evet / Hayır / Yapılamadı — parmakla basılan üç hedef (≥44 px).
class _YesNo extends StatelessWidget {
  const _YesNo({
    required this.state,
    required this.enabled,
    required this.onPick,
  });

  final String? state;
  final bool enabled;
  final void Function(String) onPick;

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final secenekler = <(String, String, Color)>[
      ('passed', S.answerYes, c.brand),
      ('failed', S.answerNo, c.critical),
      ('not_done', S.answerNotDone, c.warning),
    ];
    return Row(
      children: [
        for (final (deger, etiket, renk) in secenekler)
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(right: Gap.x2),
              child: _Pick(
                label: etiket,
                color: renk,
                selected: state == deger,
                enabled: enabled,
                onTap: () => onPick(deger),
              ),
            ),
          ),
      ],
    );
  }
}

class _Pick extends StatelessWidget {
  const _Pick({
    required this.label,
    required this.color,
    required this.selected,
    required this.enabled,
    required this.onTap,
  });

  final String label;
  final Color color;
  final bool selected;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return Semantics(
      selected: selected,
      button: true,
      child: InkWell(
        onTap: enabled ? onTap : null,
        borderRadius: BorderRadius.circular(Corner.button),
        child: Container(
          height: minTouchTarget,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: selected ? color : c.surface2,
            border: Border.all(color: selected ? color : c.line),
            borderRadius: BorderRadius.circular(Corner.button),
          ),
          child: Text(
            label,
            style: TextStyle(
              color: selected ? c.surface : c.ink2,
              fontWeight: FontWeight.w600,
              fontSize: TypeScale.label,
            ),
          ),
        ),
      ),
    );
  }
}

class _Choices extends StatelessWidget {
  const _Choices({
    required this.options,
    required this.selected,
    required this.enabled,
    required this.onPick,
  });

  final List<ChoiceOption> options;
  final String? selected;
  final bool enabled;
  final void Function(ChoiceOption) onPick;

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    if (options.isEmpty) {
      return Text(
        S.noOptions,
        style: TextStyle(color: c.muted, fontSize: TypeScale.meta),
      );
    }
    return Wrap(
      spacing: Gap.x2,
      runSpacing: Gap.x2,
      children: [
        for (final secenek in options)
          SizedBox(
            width: 140,
            child: _Pick(
              label: secenek.label,
              color: secenek.passing ? c.brand : c.critical,
              selected: selected == '"${secenek.label}"',
              enabled: enabled,
              onTap: () => onPick(secenek),
            ),
          ),
      ],
    );
  }
}

/// Sayı ve sıcaklık. Aralık dışı değer **reddedilmiyor**, başarısız
/// cevaplanıyor: ölçüm gerçeği, kural onun üstüne kurulur (BR-06).
class _NumberField extends StatefulWidget {
  const _NumberField({
    required this.item,
    required this.initial,
    required this.enabled,
    required this.onSubmit,
  });

  final RunItem item;
  final String? initial;
  final bool enabled;
  final void Function(num value, bool inRange) onSubmit;

  @override
  State<_NumberField> createState() => _NumberFieldState();
}

class _NumberFieldState extends State<_NumberField> {
  late final TextEditingController _controller = TextEditingController(
    text: widget.initial?.replaceAll('"', '') ?? '',
  );

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit(String ham) {
    final sayi = num.tryParse(ham.replaceAll(',', '.'));
    if (sayi == null) return;
    final alt = widget.item.minValue;
    final ust = widget.item.maxValue;
    final aralikta =
        (alt == null || sayi >= alt) && (ust == null || sayi <= ust);
    widget.onSubmit(sayi, aralikta);
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final aralik = widget.item.minValue != null || widget.item.maxValue != null
        ? S.range(widget.item.minValue, widget.item.maxValue, widget.item.unit)
        : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextField(
          controller: _controller,
          enabled: widget.enabled,
          keyboardType: const TextInputType.numberWithOptions(
            decimal: true,
            signed: true,
          ),
          decoration: InputDecoration(
            labelText: widget.item.unit ?? S.valueLabel,
            suffixText: widget.item.unit,
          ),
          onSubmitted: _submit,
          onTapOutside: (_) => _submit(_controller.text),
        ),
        if (aralik != null) ...[
          const SizedBox(height: Gap.x1),
          Text(
            aralik,
            style: TextStyle(color: c.muted, fontSize: TypeScale.meta),
          ),
        ],
      ],
    );
  }
}

class _TextField extends StatefulWidget {
  const _TextField({
    required this.initial,
    required this.enabled,
    required this.onSubmit,
  });

  final String? initial;
  final bool enabled;
  final void Function(String) onSubmit;

  @override
  State<_TextField> createState() => _TextFieldState();
}

class _TextFieldState extends State<_TextField> {
  late final TextEditingController _controller = TextEditingController(
    text: widget.initial == null
        ? ''
        : widget.initial!.replaceAll(RegExp(r'^"|"$'), ''),
  );

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => TextField(
    controller: _controller,
    enabled: widget.enabled,
    maxLines: 3,
    minLines: 1,
    decoration: const InputDecoration(labelText: S.valueLabel),
    onSubmitted: widget.onSubmit,
    onTapOutside: (_) {
      if (_controller.text.trim().isNotEmpty) widget.onSubmit(_controller.text);
    },
  );
}

/// Listeyi gönderme: düğme, sonuç ya da sunucunun bulduğu eksikler.
class _SubmitBar extends ConsumerStatefulWidget {
  const _SubmitBar({required this.view, required this.enabled});

  final RunView view;
  final bool enabled;

  @override
  ConsumerState<_SubmitBar> createState() => _SubmitBarState();
}

class _SubmitBarState extends ConsumerState<_SubmitBar> {
  bool _busy = false;
  SubmitOutcome? _outcome;

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _outcome = null;
    });
    final sonuc = await ref.read(submitProvider)(widget.view.runId);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _outcome = sonuc;
    });
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final sonuc = _outcome;
    final gonderilmis = sonuc is SubmitDone
        ? sonuc.view
        : (widget.view.status == 'submitted' ? widget.view : null);

    if (gonderilmis != null) {
      final basarili = gonderilmis.result != 'failed';
      return _box(
        context,
        bg: basarili ? c.brandLight : c.criticalLight,
        fg: basarili ? c.brand : c.critical,
        lines: [
          S.submitted,
          if (gonderilmis.result != null)
            S.resultLabels[gonderilmis.result] ?? gonderilmis.result!,
          if (gonderilmis.scorePercent != null)
            S.score(gonderilmis.scorePercent!),
        ],
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (sonuc is SubmitNeedsNetwork)
          _box(
            context,
            bg: c.warningLight,
            fg: c.warning,
            lines: const [S.submitNeedsNetwork],
          ),
        if (sonuc is SubmitBlocked)
          _box(
            context,
            bg: c.criticalLight,
            fg: c.critical,
            lines: [
              S.submitBlocked,
              for (final eksik in sonuc.blockers)
                '• ${eksik.title} — ${S.blockerKinds[eksik.kind] ?? eksik.kind}',
            ],
          ),
        if (sonuc is SubmitRejected) ErrorText(error: sonuc.error),
        if (sonuc != null) const SizedBox(height: Gap.x3),
        FilledButton(
          onPressed: widget.enabled && !_busy ? _submit : null,
          child: Text(_busy ? S.submitting : S.submit),
        ),
      ],
    );
  }

  Widget _box(
    BuildContext context, {
    required Color bg,
    required Color fg,
    required List<String> lines,
  }) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(Gap.x3),
    decoration: BoxDecoration(
      color: bg,
      borderRadius: BorderRadius.circular(Corner.button),
    ),
    child: Text(
      lines.join('\n'),
      style: TextStyle(color: fg, fontSize: TypeScale.label, height: 1.5),
    ),
  );
}

/// Bekleyen kayıt sayacı — kuyruk görünür olmalı, yoksa personel
/// gönderildi sanır.
class PendingBadge extends ConsumerWidget {
  const PendingBadge({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = AppColors.of(context);
    final bekleyen = ref.watch(pendingCountProvider);
    final sayi = bekleyen.value ?? 0;
    final senk = ref.watch(syncingProvider);

    // Kuyruk açılamadıysa sayaç 0 gösterilemez: "hepsi gönderildi"
    // demek, gönderilmemişken verilebilecek en pahalı yanlış bilgidir.
    if (bekleyen.hasError) {
      return Padding(
        padding: const EdgeInsets.only(right: Gap.x3),
        child: Row(
          children: [
            Icon(Icons.warning_amber_outlined, color: c.warning, size: 18),
            const SizedBox(width: Gap.x1),
            Text(
              S.queueBroken,
              style: TextStyle(color: c.warning, fontSize: TypeScale.meta),
            ),
          ],
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.only(right: Gap.x2),
      child: TextButton.icon(
        onPressed: senk ? null : () => ref.read(syncProvider)(),
        icon: senk
            ? SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: c.anchorBrand,
                ),
              )
            : Icon(
                sayi == 0
                    ? Icons.cloud_done_outlined
                    : Icons.cloud_upload_outlined,
                color: sayi == 0 ? c.anchorMuted : c.anchorBrand,
              ),
        label: Text(
          sayi == 0 ? S.allSent : S.pending(sayi),
          style: TextStyle(
            color: sayi == 0 ? c.anchorMuted : c.anchorBrand,
            fontSize: TypeScale.meta,
          ),
        ),
      ),
    );
  }
}
