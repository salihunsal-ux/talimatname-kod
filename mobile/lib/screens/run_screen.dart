/// Liste doldurma ekranı.
///
/// Cevap **önce kuyruğa** yazılır, sonra gönderilir: şubede bağlantı
/// yok sayılır. Ekranda görünen durum kuyruktan gelir, sunucudan değil
/// — personel yazdığı şeyi anında görmeli, ağın dönmesini beklememeli.
///
/// Bu sürümde fotoğraf yok (Spike C): fotoğraf isteyen madde
/// işaretleniyor ve gönderimi sunucu zaten engelliyor.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

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
    final yazilabilir = detay.view.writableAt(DateTime.now());
    // Kuyruk ayrı sağlayıcıdan: cevap yazınca yalnızca bu tazeleniyor,
    // görünüm için ağa gidilmiyor.
    final kuyruk = {
      for (final satir
          in ref.watch(queuedForRunProvider(detay.view.runId)).value ??
              const <QueuedAnswer>[])
        satir.itemId: satir,
    };

    return ListView(
      padding: const EdgeInsets.all(Gap.x4),
      children: [
        if (!yazilabilir) _notice(context, S.readOnlyWindow),
        if (detay.view.lockedByName != null)
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
                options: detay.options[madde.itemId]?.options ?? const [],
                queued: kuyruk[madde.itemId],
                enabled: yazilabilir,
              ),
            ),
        ],
        const SizedBox(height: Gap.x8),
      ],
    );
  }

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

/// Tek madde: başlık, tür bilgisi ve cevap denetimi.
class _ItemCard extends ConsumerWidget {
  const _ItemCard({
    required this.runId,
    required this.item,
    required this.options,
    required this.queued,
    required this.enabled,
  });

  final String runId;
  final RunItem item;
  final List<ChoiceOption> options;
  final QueuedAnswer? queued;
  final bool enabled;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
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

    final durum = queued?.state ?? item.serverState;
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
          if (item.photoRequired) ...[
            const SizedBox(height: Gap.x2),
            // Fotoğraf yolu Spike C'de. Maddeyi gizlemek yerine
            // söylüyoruz: personel neden gönderemediğini bilmeli.
            Text(
              S.photoNotYet,
              style: TextStyle(color: c.warning, fontSize: TypeScale.meta),
            ),
          ],
          const SizedBox(height: Gap.x3),
          _control(context, ref),
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

  Widget _control(BuildContext context, WidgetRef ref) {
    final durum = queued?.state ?? item.serverState;
    switch (item.type) {
      case 'choice':
        return _Choices(
          options: options,
          selected: queued?.valueJson,
          enabled: enabled,
          // Geçer/kalır kararını şıkkın kendisi taşıyor; sunucu da
          // aynı kuralı uyguluyor, yani ekranda görünen sonuç senkten
          // sonra değişmiyor.
          onPick: (secim) => _write(
            ref,
            secim.passing ? 'passed' : 'failed',
            value: secim.label,
          ),
        );
      case 'number':
      case 'temperature':
        return _NumberField(
          item: item,
          initial: queued?.valueJson,
          enabled: enabled,
          onSubmit: (sayi, aralikta) =>
              _write(ref, aralikta ? 'passed' : 'failed', value: sayi),
        );
      case 'text':
        return _TextField(
          initial: queued?.valueJson,
          enabled: enabled,
          onSubmit: (metin) => _write(ref, 'passed', value: metin),
        );
      default:
        return _YesNo(
          state: durum,
          enabled: enabled,
          onPick: (yeni) => _write(ref, yeni),
        );
    }
  }

  void _write(WidgetRef ref, String state, {Object? value}) {
    ref
        .read(answerProvider)(
          runId: runId,
          itemId: item.itemId,
          state: state,
          value: value,
        )
        .ignore();
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
