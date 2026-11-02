import type { ReactNode } from 'react';

/**
 * Kart: yüzey, 1 px çizgi, 12 px köşe, 16 px iç boşluk.
 * `yuzen` yalnızca sayfada tek başına duran kart için (gölge kuralı
 * tasarım sisteminde dar tutuluyor).
 */
export function Kart({
  children,
  yuzen = false,
  className,
  ...kalan
}: {
  children: ReactNode;
  yuzen?: boolean;
  className?: string;
} & React.HTMLAttributes<HTMLElement>) {
  const siniflar = ['kart', yuzen ? 'kart--yuzen' : '', className ?? ''].filter(Boolean).join(' ');
  return (
    <section className={siniflar} {...kalan}>
      {children}
    </section>
  );
}
