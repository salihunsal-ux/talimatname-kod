/// Mobil token'ları panelin CSS'inden **sapamaz**.
///
/// Neden test: bu projede renkler bir kez elle doğrulandı ve üç çift
/// aylarca kontrast eşiğinin altında kaldı (05-tasarim/04). İki istemci
/// aynı tasarım sistemini elle kopyalarsa ikisi de bir süre sonra
/// başka bir ürüne benzer. CSS tek kaynak; burası onu okuyup
/// karşılaştırıyor, yani panelde bir renk değişince mobil test kırılır.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:talimatname_saha/theme/tokens.dart';

/// CSS değişkeni → mobil karşılığı. Mobilde kullanılmayan bir token
/// yok: hepsi eşlenmeli, yoksa aşağıdaki "eksik eşleme" testi kırılır.
Color Function(AppColors) _picker(String name) => switch (name) {
  'renk-zemin' => (c) => c.background,
  'renk-yuzey' => (c) => c.surface,
  'renk-yuzey2' => (c) => c.surface2,
  'renk-murekkep' => (c) => c.ink,
  'renk-murekkep2' => (c) => c.ink2,
  'renk-sessiz' => (c) => c.muted,
  'renk-cizgi' => (c) => c.line,
  'renk-marka' => (c) => c.brand,
  'renk-marka-acik' => (c) => c.brandLight,
  'renk-kritik' => (c) => c.critical,
  'renk-kritik-acik' => (c) => c.criticalLight,
  'renk-uyari' => (c) => c.warning,
  'renk-uyari-acik' => (c) => c.warningLight,
  'renk-pasif' => (c) => c.inactive,
  'renk-koyu' => (c) => c.anchor,
  'renk-koyu-murekkep' => (c) => c.anchorInk,
  'renk-koyu-sessiz' => (c) => c.anchorMuted,
  'renk-koyu-marka' => (c) => c.anchorBrand,
  'renk-koyu-cizgi' => (c) => c.anchorLine,
  'renk-birincil-zemin' => (c) => c.primaryBg,
  'renk-birincil-yazi' => (c) => c.primaryFg,
  _ => throw StateError('eşlemesi olmayan token: $name'),
};

void main() {
  final file = File('../web/src/styles/tokens.css');

  test('CSS tek kaynak dosyası yerinde', () {
    expect(
      file.existsSync(),
      isTrue,
      reason: 'tokens.css bulunamadı: ${file.absolute.path}',
    );
  });

  final css = file.readAsStringSync();
  final light = _parseBlock(css, ':root {');
  final dark = _parseBlock(css, ":root[data-tema='koyu'] {");

  test('açık tema renkleri CSS ile aynı', () {
    _compare(light, AppColors.light);
  });

  test('koyu tema renkleri CSS ile aynı', () {
    // Koyu blok yalnızca **değişen** token'ları yazıyor; yazılmayanlar
    // açık temadan miras. Karşılaştırma da öyle.
    _compare({...light, ...dark}, AppColors.dark);
  });

  test('sistem teması bloğu ile açık koyu blok aynı değerleri veriyor', () {
    // CSS'te koyu tema iki yerde: elle seçilen (`data-tema='koyu'`) ve
    // sistemden gelen (`prefers-color-scheme`). İkisi ayrışırsa
    // kullanıcı temayı nasıl seçtiğine göre başka renk görür.
    final sistem = _parseBlock(css, ":root:not([data-tema='acik']) {");
    expect(sistem, isNotEmpty, reason: 'sistem teması bloğu okunamadı');
    expect(sistem, dark);
  });

  test('CSS renk token’larının hepsi mobilde eşlenmiş', () {
    for (final name in light.keys) {
      expect(
        () => _picker(name),
        returnsNormally,
        reason:
            '$name mobilde karşılıksız: token eklendiyse buraya da eklenmeli',
      );
    }
  });
}

void _compare(Map<String, Color> expected, AppColors actual) {
  for (final entry in expected.entries) {
    expect(
      _picker(entry.key)(actual),
      entry.value,
      reason: '${entry.key} CSS ile uyuşmuyor',
    );
  }
}

/// Verilen blok başlığından ilk kapanışa kadarki `--renk-*`
/// değerlerini okur.
///
/// Kaba bir ayrıştırıcı ve bilerek öyle: CSS'i gerçekten yorumlamak
/// testin kendi hatası olurdu. Önce "koyu tema bloğundan öncesi açık
/// temadır" diye yazılmıştı ve `data-tema='koyu'` bloğu açık temanın
/// içinde kalıyordu — test kendi kaynağını yanlış okuyordu. Blok
/// sınırı artık başlıktan ve ilk kapanış satırından geliyor.
Map<String, Color> _parseBlock(String css, String header) {
  final start = css.indexOf(header);
  if (start == -1) return const {};
  final body = css.substring(start + header.length);
  final end = body.indexOf('\n}');
  final region = body.substring(0, end == -1 ? body.length : end);

  final result = <String, Color>{};
  final pattern = RegExp(r'--(renk-[a-z0-9-]+):\s*#([0-9a-fA-F]{6})\s*;');
  for (final match in pattern.allMatches(region)) {
    result[match.group(1)!] = Color(
      0xFF000000 | int.parse(match.group(2)!, radix: 16),
    );
  }
  return result;
}
