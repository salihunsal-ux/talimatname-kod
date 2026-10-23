import type { ReactNode } from 'react';

import type { Ben } from '../api/oturum';
import { OturumBaglami } from '../api/yetki';
import { YONETICI } from './kullanicilar';

/** Sayfaları oturumlu kurar: rol kapıları test içinde de geçerli. */
export function Oturumlu({ children, ben = YONETICI }: { children: ReactNode; ben?: Ben | null }) {
  return <OturumBaglami value={ben}>{children}</OturumBaglami>;
}
