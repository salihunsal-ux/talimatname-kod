/// Giriş: telefon → kod. İki adım tek ekranda.
library;

import 'package:material_ui/material_ui.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/problem.dart';
import '../l10n/strings.dart';
import '../state/providers.dart';
import '../theme/tokens.dart';
import '../widgets/error_text.dart';

class SignInScreen extends ConsumerStatefulWidget {
  const SignInScreen({super.key});

  @override
  ConsumerState<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends ConsumerState<SignInScreen> {
  final _phone = TextEditingController();
  final _code = TextEditingController();

  bool _codeRequested = false;
  bool _busy = false;
  String? _devCode;
  ApiException? _error;

  @override
  void dispose() {
    _phone.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() work) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await work();
    } on ApiException catch (hata) {
      if (mounted) setState(() => _error = hata);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _requestCode() => _run(() async {
    final code = await ref
        .read(sessionProvider.notifier)
        .requestCode(_phone.text.trim());
    if (!mounted) return;
    setState(() {
      _codeRequested = true;
      _devCode = code;
    });
  });

  Future<void> _verify() => _run(
    () => ref
        .read(sessionProvider.notifier)
        .verify(_phone.text.trim(), _code.text.trim()),
  );

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return Scaffold(
      backgroundColor: c.anchor,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(Gap.x6),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    S.appTitle,
                    style: TextStyle(
                      color: c.anchorInk,
                      fontSize: TypeScale.screenTitle,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: Gap.x1),
                  Text(
                    S.tagline,
                    style: TextStyle(
                      color: c.anchorMuted,
                      fontSize: TypeScale.meta,
                      letterSpacing: 1,
                    ),
                  ),
                  const SizedBox(height: Gap.x8),
                  _card(context),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _card(BuildContext context) {
    final c = AppColors.of(context);
    return Container(
      padding: const EdgeInsets.all(Gap.x4),
      decoration: BoxDecoration(
        color: c.surface,
        border: Border.all(color: c.line),
        borderRadius: BorderRadius.circular(Corner.card),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(S.signInTitle, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: Gap.x1),
          Text(S.signInHint, style: Theme.of(context).textTheme.labelSmall),
          const SizedBox(height: Gap.x4),
          TextField(
            controller: _phone,
            enabled: !_codeRequested && !_busy,
            keyboardType: TextInputType.phone,
            autofillHints: const [AutofillHints.telephoneNumber],
            decoration: const InputDecoration(
              labelText: S.phoneLabel,
              hintText: S.phoneExample,
            ),
            onSubmitted: (_) {
              if (!_codeRequested) _requestCode();
            },
          ),
          if (_codeRequested) ...[
            const SizedBox(height: Gap.x3),
            TextField(
              controller: _code,
              enabled: !_busy,
              autofocus: true,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: S.codeLabel),
              onSubmitted: (_) => _verify(),
            ),
            // Kod ekranda, çünkü SMS sağlayıcısı bağlı değil. Metin
            // "geliştirme" demiyor: demo kurulumunda da bu görünüyor.
            if (_devCode != null) ...[
              const SizedBox(height: Gap.x3),
              _notice(
                context,
                '${S.smsNotConnected}\n${S.codeOnScreen(_devCode!)}',
              ),
            ],
          ],
          if (_error != null) ...[
            const SizedBox(height: Gap.x3),
            ErrorText(error: _error!),
          ],
          const SizedBox(height: Gap.x4),
          FilledButton(
            onPressed: _busy ? null : (_codeRequested ? _verify : _requestCode),
            child: Text(
              _busy ? '…' : (_codeRequested ? S.signIn : S.requestCode),
            ),
          ),
          if (_codeRequested)
            TextButton(
              onPressed: _busy
                  ? null
                  : () => setState(() {
                      _codeRequested = false;
                      _devCode = null;
                      _code.clear();
                      _error = null;
                    }),
              child: const Text(S.changePhone),
            ),
        ],
      ),
    );
  }

  Widget _notice(BuildContext context, String text) {
    final c = AppColors.of(context);
    return Container(
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
