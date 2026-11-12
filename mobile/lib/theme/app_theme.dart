/// Token'lardan `ThemeData`. Renk kararları [AppColors] içinde;
/// burası yalnızca Flutter'ın beklediği şekle çeviriyor.
library;

import 'package:material_ui/material_ui.dart';

import 'tokens.dart';

const _fontFamilyFallback = <String>[
  'Segoe UI',
  'SF Pro Text',
  'Roboto',
  'system-ui',
];

ThemeData buildTheme(Brightness brightness) {
  final c = brightness == Brightness.dark ? AppColors.dark : AppColors.light;
  final base = ThemeData(brightness: brightness, useMaterial3: true);

  return base.copyWith(
    scaffoldBackgroundColor: c.background,
    colorScheme:
        ColorScheme.fromSeed(
          seedColor: c.brand,
          brightness: brightness,
        ).copyWith(
          surface: c.surface,
          onSurface: c.ink,
          primary: c.brand,
          error: c.critical,
          outline: c.line,
        ),
    textTheme: _textTheme(base.textTheme, c),
    dividerColor: c.line,
    cardTheme: CardThemeData(
      color: c.surface,
      elevation: 0,
      shape: RoundedRectangleBorder(
        side: BorderSide(color: c.line),
        borderRadius: BorderRadius.circular(Corner.card),
      ),
      margin: EdgeInsets.zero,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: c.surface,
      contentPadding: const EdgeInsets.symmetric(
        horizontal: Gap.x4,
        vertical: Gap.x3,
      ),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(Corner.button),
        borderSide: BorderSide(color: c.line),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(Corner.button),
        borderSide: BorderSide(color: c.line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(Corner.button),
        borderSide: BorderSide(color: c.brand, width: 2),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: c.primaryBg,
        foregroundColor: c.primaryFg,
        minimumSize: const Size.fromHeight(minTouchTarget),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Corner.button),
        ),
        textStyle: const TextStyle(
          fontSize: TypeScale.body,
          fontWeight: FontWeight.w600,
        ),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: c.brand,
        minimumSize: const Size(minTouchTarget, minTouchTarget),
      ),
    ),
  );
}

TextTheme _textTheme(TextTheme base, AppColors c) => base
    .copyWith(
      headlineSmall: TextStyle(
        fontSize: TypeScale.screenTitle,
        fontWeight: FontWeight.w700,
        color: c.ink,
      ),
      titleMedium: TextStyle(
        fontSize: TypeScale.sectionTitle,
        fontWeight: FontWeight.w600,
        color: c.ink,
      ),
      bodyLarge: TextStyle(
        fontSize: TypeScale.body,
        height: TypeScale.bodyHeight,
        color: c.ink,
      ),
      bodyMedium: TextStyle(
        fontSize: TypeScale.body,
        height: TypeScale.bodyHeight,
        color: c.ink2,
      ),
      labelLarge: TextStyle(
        fontSize: TypeScale.label,
        fontWeight: FontWeight.w500,
        color: c.ink,
      ),
      labelSmall: TextStyle(fontSize: TypeScale.meta, color: c.muted),
    )
    .apply(fontFamilyFallback: _fontFamilyFallback);
