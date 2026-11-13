/// Uygulama içi kamera: çek, sıkıştır, geri dön.
///
/// **Galeri yolu yok** ve bilerek yok (FR-0602): kanıtın değeri, o anda
/// o yerde çekilmiş olmasından geliyor. Bu ekranda dosya seçici, galeri
/// düğmesi ya da paylaşım hedefi bulunmuyor; fotoğraf yalnızca
/// deklanşörle üretilir.
///
/// Damga (şube · tarih-saat · kullanıcı) **sunucuda** basılıyor; cihaz
/// yalnızca ham kareyi sıkıştırıp özetini çıkarıyor. Cihazda damga
/// basmak, saati yanlış bir telefonun yanlış damga üretmesi demek olurdu.
library;

import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter_image_compress/flutter_image_compress.dart';
import 'package:material_ui/material_ui.dart';

import '../l10n/strings.dart';
import '../theme/tokens.dart';

/// Hedef dosya boyutu (Spike C kabulü: ≤ 300 KB, okunur).
const targetPhotoBytes = 300 * 1024;

/// Kareyi hedef boyuta indirir. Önce uzun kenar 1600 px'e çekilir, sonra
/// kalite adım adım düşürülür; okunurluk boyuttan önce gelir, o yüzden
/// kalite 40'ın altına inilmez — hedefi tutturamayan kare olduğu gibi
/// döner ve sunucunun 3 MB sınırı son sözü söyler.
Future<Uint8List> compressPhoto(String path) async {
  Uint8List? sonuc;
  for (final kalite in const [75, 60, 50, 40]) {
    sonuc = await FlutterImageCompress.compressWithFile(
      path,
      minWidth: 1600,
      minHeight: 1600,
      quality: kalite,
      format: CompressFormat.jpeg,
    );
    if (sonuc != null && sonuc.length <= targetPhotoBytes) return sonuc;
  }
  if (sonuc == null) throw StateError('fotoğraf sıkıştırılamadı');
  return sonuc;
}

class CameraScreen extends StatefulWidget {
  const CameraScreen({super.key});

  @override
  State<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends State<CameraScreen> {
  CameraController? _controller;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _open();
  }

  Future<void> _open() async {
    try {
      final kameralar = await availableCameras();
      if (kameralar.isEmpty) {
        setState(() => _error = S.cameraMissing);
        return;
      }
      // Arka kamera: kanıt karşıdaki şeyin fotoğrafıdır, özçekim değil.
      final arka = kameralar.firstWhere(
        (k) => k.lensDirection == CameraLensDirection.back,
        orElse: () => kameralar.first,
      );
      final controller = CameraController(
        arka,
        ResolutionPreset.high,
        enableAudio: false,
      );
      await controller.initialize();
      if (!mounted) {
        await controller.dispose();
        return;
      }
      setState(() => _controller = controller);
    } on CameraException catch (hata) {
      if (!mounted) return;
      setState(
        () => _error = hata.code == 'CameraAccessDenied'
            ? S.cameraDenied
            : S.cameraFailed,
      );
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  Future<void> _shoot() async {
    final controller = _controller;
    if (controller == null || _busy) return;
    setState(() => _busy = true);
    try {
      final kare = await controller.takePicture();
      final baytlar = await compressPhoto(kare.path);
      if (!mounted) return;
      Navigator.of(context).pop(baytlar);
    } on Object {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = S.cameraFailed;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final controller = _controller;
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (controller != null)
              Center(child: CameraPreview(controller))
            else if (_error == null)
              const Center(child: CircularProgressIndicator()),
            if (_error != null)
              Center(
                child: Padding(
                  padding: const EdgeInsets.all(Gap.x6),
                  child: Text(
                    _error!,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: c.anchorInk,
                      fontSize: TypeScale.body,
                    ),
                  ),
                ),
              ),
            Positioned(
              top: Gap.x2,
              left: Gap.x2,
              child: IconButton(
                tooltip: S.cameraClose,
                onPressed: () => Navigator.of(context).pop(),
                icon: Icon(Icons.close, color: c.anchorInk, size: 28),
              ),
            ),
            if (controller != null)
              Positioned(
                bottom: Gap.x8,
                left: 0,
                right: 0,
                child: Center(
                  child: Semantics(
                    button: true,
                    label: S.cameraShoot,
                    child: GestureDetector(
                      onTap: _shoot,
                      child: Container(
                        width: 76,
                        height: 76,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: _busy ? c.anchorMuted : c.anchorInk,
                          border: Border.all(color: c.anchorBrand, width: 4),
                        ),
                        child: _busy
                            ? const Padding(
                                padding: EdgeInsets.all(22),
                                child: CircularProgressIndicator(
                                  strokeWidth: 3,
                                ),
                              )
                            : null,
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
