import type { ButtonHTMLAttributes } from 'react';

type Gorunum = 'birincil' | 'ikincil' | 'sessiz';

/**
 * Düğme. Görünüm token'lardan, haller (hover · active · disabled) CSS
 * sınıfından geliyor: satır içi stil bu halleri yazamıyor.
 */
export function Dugme({
  gorunum = 'birincil',
  tam = false,
  className,
  ...kalan
}: ButtonHTMLAttributes<HTMLButtonElement> & { gorunum?: Gorunum; tam?: boolean }) {
  const siniflar = ['dugme', `dugme--${gorunum}`, tam ? 'dugme--tam' : '', className ?? '']
    .filter(Boolean)
    .join(' ');

  return <button className={siniflar} {...kalan} />;
}
