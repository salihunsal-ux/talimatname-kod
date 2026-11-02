import type { ButtonHTMLAttributes } from 'react';

type Gorunum = 'birincil' | 'ikincil' | 'sessiz';
type Boyut = 'kucuk';

/**
 * Düğme. Görünüm token'lardan, haller (hover · active · disabled) CSS
 * sınıfından geliyor: satır içi stil bu halleri yazamıyor.
 */
export function Dugme({
  gorunum = 'birincil',
  boyut,
  tam = false,
  className,
  ...kalan
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  gorunum?: Gorunum;
  boyut?: Boyut;
  tam?: boolean;
}) {
  const siniflar = [
    'dugme',
    `dugme--${gorunum}`,
    boyut ? `dugme--${boyut}` : '',
    tam ? 'dugme--tam' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');

  return <button className={siniflar} {...kalan} />;
}
