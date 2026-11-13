/// Talimatname saha istemcisi.
///
/// Bu sürüm **ilk dikey dilim**: giriş → bugünün listeleri. Çevrimdışı
/// kuyruk, madde doldurma ve kanıt çekme yok; sözleşmenin uçtan uca
/// gerçek sunucuya karşı çalıştığını göstermek için var.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import 'l10n/strings.dart';
import 'screens/sign_in_screen.dart';
import 'screens/today_screen.dart';
import 'state/providers.dart';
import 'theme/app_theme.dart';
import 'widgets/auto_sync.dart';

void main() {
  runApp(const ProviderScope(child: TalimatnameApp()));
}

class TalimatnameApp extends StatelessWidget {
  const TalimatnameApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: S.appTitle,
    debugShowCheckedModeBanner: false,
    theme: buildTheme(Brightness.light),
    darkTheme: buildTheme(Brightness.dark),
    home: const AutoSync(child: _Root()),
  );
}

class _Root extends ConsumerWidget {
  const _Root();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    return session.when(
      // Saklanan oturum okunurken boş ekran: giriş ekranını gösterip
      // bir an sonra kapatmak, her açılışta "çıkmışım" hissi verir.
      loading: () =>
          const Scaffold(body: Center(child: CircularProgressIndicator())),
      error: (_, _) => const SignInScreen(),
      data: (data) => data == null ? const SignInScreen() : const TodayScreen(),
    );
  }
}
