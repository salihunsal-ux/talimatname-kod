/// Maddenin fotoğrafları: küçük resim şeridi, büyütme ve (yalnızca
/// yüklenmemişse) silme.
///
/// **Yüklenmiş kanıt silinemez** ve bu bir eksik değil, ürünün sözü:
/// sunucuya ulaşan kanıt değiştirilemez kayıttır (FR-0609 "kanıt
/// silinmez"). Silme yalnızca cihazdan çıkmamış kare için var. Yanlış
/// karenin kayda girmesini kamera ekranındaki önizleme engelliyor.
library;

import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../l10n/strings.dart';
import '../queue/database.dart';
import '../state/run_providers.dart';
import '../theme/tokens.dart';

class EvidenceStrip extends ConsumerWidget {
  const EvidenceStrip({
    required this.runId,
    required this.evidence,
    required this.enabled,
    super.key,
  });

  final String runId;
  final List<QueuedEvidenceData> evidence;
  final bool enabled;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final gorunen = [
      for (final k in evidence)
        if (!k.blocked) k,
    ];
    if (gorunen.isEmpty) return const SizedBox.shrink();
    return Wrap(
      spacing: Gap.x2,
      runSpacing: Gap.x2,
      children: [
        for (final k in gorunen)
          _Thumb(
            evidence: k,
            onOpen: () => Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => _Viewer(evidence: k)),
            ),
            onRemove: enabled && !k.uploaded
                ? () => ref.read(removePhotoProvider)(
                    runId: runId,
                    evidenceId: k.evidenceId,
                  )
                : null,
          ),
      ],
    );
  }
}

class _Thumb extends StatelessWidget {
  const _Thumb({
    required this.evidence,
    required this.onOpen,
    required this.onRemove,
  });

  final QueuedEvidenceData evidence;
  final VoidCallback onOpen;
  final VoidCallback? onRemove;

  static const _size = 72.0;

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return SizedBox(
      width: _size,
      height: _size,
      child: Stack(
        children: [
          Positioned.fill(
            child: InkWell(
              onTap: onOpen,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(Corner.button),
                child: _EvidenceImage(
                  evidence: evidence,
                  variant: 'thumbnail',
                  fit: BoxFit.cover,
                ),
              ),
            ),
          ),
          if (onRemove != null)
            Positioned(
              top: 0,
              right: 0,
              // Dokunma hedefi görünenden büyük: 44 px kuralı küçük
              // resmin köşesinde de geçerli.
              child: Semantics(
                button: true,
                label: S.photoRemove,
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: onRemove,
                  child: Container(
                    width: 36,
                    height: 36,
                    alignment: Alignment.topRight,
                    child: Container(
                      width: 24,
                      height: 24,
                      decoration: BoxDecoration(
                        color: c.critical,
                        shape: BoxShape.circle,
                      ),
                      child: Icon(Icons.close, size: 16, color: c.surface),
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Fotoğrafın kendisi: cihazdaysa dosyadan, yüklendiyse sunucudan.
///
/// Yüklenen karenin cihazdaki kopyası siliniyor (depo sınırlı); o yüzden
/// yüklenmiş fotoğraf **bağlantı varken** görünür. Bağlantı yoksa yer
/// tutucu çıkar; fotoğraf kaybolmuş değil, sunucuda.
class _EvidenceImage extends ConsumerWidget {
  const _EvidenceImage({
    required this.evidence,
    required this.variant,
    required this.fit,
  });

  final QueuedEvidenceData evidence;
  final String variant;
  final BoxFit fit;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = AppColors.of(context);
    Widget yerTutucu(IconData ikon) => ColoredBox(
      color: c.surface2,
      child: Center(child: Icon(ikon, color: c.muted)),
    );

    final dosya = File(evidence.filePath);
    if (dosya.existsSync()) {
      return Image.file(
        dosya,
        fit: fit,
        errorBuilder: (_, _, _) => yerTutucu(Icons.broken_image_outlined),
      );
    }
    final adres = ref.watch(
      evidenceUrlProvider((id: evidence.evidenceId, variant: variant)),
    );
    return adres.when(
      loading: () => yerTutucu(Icons.image_outlined),
      error: (_, _) => yerTutucu(Icons.cloud_off_outlined),
      data: (url) => Image.network(
        url,
        fit: fit,
        errorBuilder: (_, _, _) => yerTutucu(Icons.cloud_off_outlined),
      ),
    );
  }
}

class _Viewer extends StatelessWidget {
  const _Viewer({required this.evidence});

  final QueuedEvidenceData evidence;

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: c.anchorInk,
        title: Text(
          evidence.uploaded ? S.photoOnServer : S.photoPending,
          style: const TextStyle(fontSize: TypeScale.label),
        ),
      ),
      body: Center(
        child: InteractiveViewer(
          // Yüklenmiş karenin damgalı hâli gösterilir: dışarı giden
          // kopya odur.
          child: _EvidenceImage(
            evidence: evidence,
            variant: 'stamped',
            fit: BoxFit.contain,
          ),
        ),
      ),
    );
  }
}
