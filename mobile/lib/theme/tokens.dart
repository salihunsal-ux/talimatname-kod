/// Tasarım token'ları — tek kaynak `web/src/styles/tokens.css`.
///
/// Değerler elle kopyalanmadı sayılmaz: `test/tokens_match_css_test.dart`
/// CSS'i okuyup burayla karşılaştırıyor. Panelde bir renk değişirse
/// mobil test kırmızıya döner. Elle doğrulama bu projede bir kez
/// denendi ve üç renk çifti aylarca kontrast eşiğinin altında kaldı
/// (05-tasarim/04).
library;

import 'package:material_ui/material_ui.dart';

/// Tema renkleri. `ThemeExtension` yerine düz sınıf: geçiş animasyonu
/// (lerp) bu üründe hiçbir yerde kullanılmıyor, 21 alan için lerp
/// yazmak okunmayan kod olurdu.
class AppColors {
  const AppColors({
    required this.background,
    required this.surface,
    required this.surface2,
    required this.ink,
    required this.ink2,
    required this.muted,
    required this.line,
    required this.brand,
    required this.brandLight,
    required this.critical,
    required this.criticalLight,
    required this.warning,
    required this.warningLight,
    required this.inactive,
    required this.anchor,
    required this.anchorInk,
    required this.anchorMuted,
    required this.anchorBrand,
    required this.anchorLine,
    required this.primaryBg,
    required this.primaryFg,
  });

  final Color background;
  final Color surface;
  final Color surface2;
  final Color ink;
  final Color ink2;
  final Color muted;
  final Color line;
  final Color brand;
  final Color brandLight;
  final Color critical;
  final Color criticalLight;
  final Color warning;
  final Color warningLight;
  final Color inactive;

  /// Temadan bağımsız koyu yüzey (üst bant, giriş paneli). Açık temada
  /// da koyu; üstündeki metin ve vurgu ayrı token, çünkü açık tema
  /// renkleri bu zeminde okunmuyor.
  final Color anchor;
  final Color anchorInk;
  final Color anchorMuted;
  final Color anchorBrand;
  final Color anchorLine;

  /// Birincil düğme sayfanın tersi: her iki temada sayfadan ~15:1.
  final Color primaryBg;
  final Color primaryFg;

  static const light = AppColors(
    background: Color(0xFFF7F5EF),
    surface: Color(0xFFFFFFFF),
    surface2: Color(0xFFEFECE4),
    ink: Color(0xFF1C2128),
    ink2: Color(0xFF4B5560),
    muted: Color(0xFF5B6670),
    line: Color(0xFFD6D9D2),
    brand: Color(0xFF1F6F5B),
    brandLight: Color(0xFFDCEBE5),
    critical: Color(0xFFA63D29),
    criticalLight: Color(0xFFF3DDD8),
    warning: Color(0xFF8C5D16),
    warningLight: Color(0xFFF6EBD2),
    inactive: Color(0xFFC9CED6),
    anchor: Color(0xFF16201D),
    anchorInk: Color(0xFFF1EEE6),
    anchorMuted: Color(0xFF9AA2A8),
    anchorBrand: Color(0xFF3FA98C),
    anchorLine: Color(0xFF16201D),
    primaryBg: Color(0xFF16201D),
    primaryFg: Color(0xFFF1EEE6),
  );

  static const dark = AppColors(
    background: Color(0xFF15191C),
    surface: Color(0xFF1D2226),
    surface2: Color(0xFF262C31),
    ink: Color(0xFFF1EEE6),
    ink2: Color(0xFFB5BCC4),
    muted: Color(0xFF929AA1),
    line: Color(0xFF2F373D),
    brand: Color(0xFF45B394),
    brandLight: Color(0xFF173A31),
    critical: Color(0xFFE46F5A),
    criticalLight: Color(0xFF3A201B),
    warning: Color(0xFFE0A640),
    warningLight: Color(0xFF33290F),
    inactive: Color(0xFF3A424A),
    anchor: Color(0xFF1E2A26),
    anchorInk: Color(0xFFF1EEE6),
    anchorMuted: Color(0xFF9AA2A8),
    anchorBrand: Color(0xFF3FA98C),
    anchorLine: Color(0xFF324039),
    primaryBg: Color(0xFFF1EEE6),
    primaryFg: Color(0xFF15191C),
  );

  static AppColors of(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? dark : light;
}

/// Boşluk ölçeği. 20 ve 28 **bilerek yok**: ara değer isteyen bir
/// yerleşim, yanlış yerleşimdir (05-tasarim/04).
abstract final class Gap {
  static const x1 = 4.0;
  static const x2 = 8.0;
  static const x3 = 12.0;
  static const x4 = 16.0;
  static const x6 = 24.0;
  static const x8 = 32.0;
}

abstract final class Corner {
  static const card = 12.0;
  static const button = 10.0;
  static const chip = 999.0;
}

/// Tipografi. Gövde mobilde 16 (webde 14): parmakla okunan metin.
abstract final class TypeScale {
  static const screenTitle = 22.0;
  static const sectionTitle = 17.0;
  static const body = 16.0;
  static const label = 13.0;
  static const meta = 12.0;
  static const bodyHeight = 1.45;
}

/// Dokunma hedefi alt sınırı; küçük düğme istisnası mobilde yok.
const double minTouchTarget = 44.0;
