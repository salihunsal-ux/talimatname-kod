/// Bugünün listeleri: manifestten gelen çalıştırmalar.
///
/// Pencere bilgisi sunucudan geliyor ve ekranda **yerel** saatle
/// gösteriliyor. "Şimdi açık" kararı `writable_from`/`tolerance_end`
/// ile veriliyor (BR-02a): penceresi açılmamış listeye dokunma daveti
/// çıkmaz, çünkü sunucu `pencere-acilmadi` ile reddeder.
library;

import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/models.dart';
import '../api/problem.dart';
import '../l10n/strings.dart';
import '../state/providers.dart';
import '../theme/tokens.dart';
import '../widgets/error_text.dart';

class TodayScreen extends ConsumerWidget {
  const TodayScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = AppColors.of(context);
    final manifest = ref.watch(manifestProvider);
    final session = ref.watch(sessionProvider).value;

    return Scaffold(
      appBar: AppBar(
        backgroundColor: c.anchor,
        foregroundColor: c.anchorInk,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              S.todayTitle,
              style: TextStyle(
                fontSize: TypeScale.sectionTitle,
                fontWeight: FontWeight.w600,
              ),
            ),
            if (session != null)
              Text(
                session.fullName,
                style: TextStyle(
                  fontSize: TypeScale.meta,
                  color: c.anchorMuted,
                ),
              ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: S.refresh,
            onPressed: () => ref.invalidate(manifestProvider),
            icon: const Icon(Icons.refresh),
          ),
          IconButton(
            tooltip: S.signOut,
            onPressed: () => ref.read(sessionProvider.notifier).signOut(),
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(manifestProvider),
        child: manifest.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (hata, _) => _error(context, ref, hata),
          data: (data) => _list(context, data),
        ),
      ),
    );
  }

  Widget _error(BuildContext context, WidgetRef ref, Object hata) => ListView(
    padding: const EdgeInsets.all(Gap.x4),
    children: [
      ErrorText(
        error: hata is ApiException
            ? hata
            : ApiException(statusCode: 0, type: '${urnPrefix}bilinmeyen'),
      ),
      const SizedBox(height: Gap.x3),
      FilledButton(
        onPressed: () => ref.invalidate(manifestProvider),
        child: const Text(S.retry),
      ),
    ],
  );

  Widget _list(BuildContext context, Manifest manifest) {
    if (manifest.runs.isEmpty) return _empty(context);
    final now = DateTime.now();
    // Yazılabilir olanlar üstte, sonra açılış saatine göre: personelin
    // ilk gördüğü şey **şimdi yapılabilecek** iş olmalı.
    final runs = [...manifest.runs]
      ..sort((a, b) {
        final ai = a.writableAt(now) ? 0 : 1;
        final bi = b.writableAt(now) ? 0 : 1;
        return ai != bi ? ai - bi : a.windowStart.compareTo(b.windowStart);
      });
    return ListView.separated(
      padding: const EdgeInsets.all(Gap.x4),
      itemCount: runs.length,
      separatorBuilder: (_, _) => const SizedBox(height: Gap.x3),
      itemBuilder: (context, i) => _RunCard(run: runs[i], now: now),
    );
  }

  Widget _empty(BuildContext context) => ListView(
    padding: const EdgeInsets.all(Gap.x6),
    children: [
      const SizedBox(height: Gap.x8),
      Text(
        S.todayEmpty,
        textAlign: TextAlign.center,
        style: Theme.of(context).textTheme.titleMedium,
      ),
      const SizedBox(height: Gap.x2),
      Text(
        S.todayEmptyHint,
        textAlign: TextAlign.center,
        style: Theme.of(context).textTheme.labelSmall,
      ),
    ],
  );
}

class _RunCard extends StatelessWidget {
  const _RunCard({required this.run, required this.now});

  final ManifestRun run;
  final DateTime now;

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final writable = run.writableAt(now);
    return Container(
      padding: const EdgeInsets.all(Gap.x4),
      decoration: BoxDecoration(
        color: c.surface,
        border: Border.all(color: writable ? c.brand : c.line),
        borderRadius: BorderRadius.circular(Corner.card),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  run.planName,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              _StatusChip(run: run, now: now),
            ],
          ),
          const SizedBox(height: Gap.x1),
          Text(
            // Ufuk 48 saat: manifestte yarının listeleri de var ve
            // şube + plan + saat aynı olduğu için kartlar birbirinin
            // kopyası görünüyordu. Gün, bugün değilse yazılır.
            _dayLabel(run.businessDay) == null
                ? run.branchName
                : '${run.branchName} · ${_dayLabel(run.businessDay)}',
            style: Theme.of(context).textTheme.labelSmall,
          ),
          const SizedBox(height: Gap.x3),
          Text(
            S.windowRange(_hhmm(run.windowStart), _hhmm(run.windowEnd)),
            style: TextStyle(
              color: c.ink2,
              fontSize: TypeScale.label,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
        ],
      ),
    );
  }

  /// `null` = bugün, yani ekranda gün yazmaya gerek yok.
  static String? _dayLabel(String businessDay) {
    final day = DateTime.tryParse(businessDay);
    if (day == null) return businessDay;
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final diff = DateTime(
      day.year,
      day.month,
      day.day,
    ).difference(today).inDays;
    if (diff == 0) return null;
    if (diff == 1) return S.tomorrow;
    return '${day.day} ${S.months[day.month - 1]}';
  }

  static String _hhmm(DateTime t) {
    final local = t.toLocal();
    return '${local.hour.toString().padLeft(2, '0')}:'
        '${local.minute.toString().padLeft(2, '0')}';
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.run, required this.now});

  final ManifestRun run;
  final DateTime now;

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final (text, fg, bg) = _look(c);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: Gap.x3, vertical: Gap.x1),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(Corner.chip),
      ),
      child: Text(
        text,
        style: TextStyle(
          color: fg,
          fontSize: TypeScale.label,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  /// Durum çifti (metin + zemin) **tek yerde**; panelin `.durum--*`
  /// sınıflarıyla aynı eşleme.
  (String, Color, Color) _look(AppColors c) {
    if (run.status == 'missed') {
      return (S.status['missed']!, c.critical, c.criticalLight);
    }
    if (run.status == 'submitted') {
      return (S.status['submitted']!, c.brand, c.brandLight);
    }
    if (run.status == 'cancelled') {
      return (S.status['cancelled']!, c.muted, c.surface2);
    }
    if (run.writableAt(now)) return (S.openNow, c.brand, c.brandLight);
    if (!run.openedBy(now)) return (S.notYetOpen, c.muted, c.surface2);
    return (S.windowClosed, c.warning, c.warningLight);
  }
}
