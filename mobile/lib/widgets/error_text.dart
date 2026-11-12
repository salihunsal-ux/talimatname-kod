/// Hata metni. **`type`'a göre** metin seçer; sunucunun Türkçe
/// `title`'ını doğrudan basmaz (ADR-0014 md.8): `title` değişebilir,
/// `type` sözleşmedir. Bilinmeyen kodda genel metin gösterilir, ama
/// alan hataları varsa onlar gösterilir — kullanıcıya yapacağını
/// söyleyen tek şey onlar.
library;

import 'package:material_ui/material_ui.dart';

import '../api/problem.dart';
import '../l10n/strings.dart';
import '../theme/tokens.dart';

/// Bilinen kodların kullanıcı metni. Listede olmayan kod genel metne
/// düşer; makine kodu ekrana çıkmaz.
const _messages = <String, String>{
  'aglanamadi': S.networkError,
  'gecersiz-kod': 'Kod doğru değil. Tekrar deneyin.',
  'kod-suresi-doldu': 'Kodun süresi doldu. Yeni kod isteyin.',
  'cok-erken-tekrar': 'Çok sık denendi. Bir dakika sonra tekrar deneyin.',
  'cok-fazla-deneme': 'Çok fazla deneme yapıldı. Biraz sonra tekrar deneyin.',
  'kullanici-yok': 'Bu numara kayıtlı değil. Şube müdürünüze başvurun.',
  'oturum-yok': S.sessionEnded,
  'pencere-acilmadi': 'Liste henüz açılmadı.',
  'pencere-kapali': 'Pencere kapandı.',
};

class ErrorText extends StatelessWidget {
  const ErrorText({required this.error, super.key});

  final ApiException error;

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final fields = error.fieldErrors;
    final text = fields.isNotEmpty
        ? fields.map((f) => f.reason).join('\n')
        : (_messages[error.code] ?? S.genericError);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(Gap.x3),
      decoration: BoxDecoration(
        color: c.criticalLight,
        borderRadius: BorderRadius.circular(Corner.button),
      ),
      child: Text(
        text,
        style: TextStyle(color: c.critical, fontSize: TypeScale.label),
      ),
    );
  }
}
