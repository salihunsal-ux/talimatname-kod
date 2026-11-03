/**
 * Marka işareti: sayfa + mühür (tasarım sistemi · İkonografi).
 *
 * İsimden bağımsız çizildi — isim testi hangi sonucu verirse versin
 * işaret kullanılabilir; değişecek olan yanındaki yazı.
 *
 * Koyu zeminde `koyu` sürümü kullanılıyor: açık tema yeşili mürekkep
 * üstünde yeterince okunmuyor.
 */
export function Marka({ boyut = 26, koyu = false }: { boyut?: number; koyu?: boolean }) {
  const sayfa = koyu ? 'var(--renk-koyu-marka)' : 'var(--renk-marka)';
  const muhur = koyu ? '#e46f5a' : 'var(--renk-kritik)';
  const tik = koyu ? 'var(--renk-koyu)' : '#fff';

  return (
    <svg width={boyut} height={boyut} viewBox="0 0 28 28" aria-hidden="true" focusable="false">
      <rect
        x="4"
        y="2.5"
        width="16"
        height="21"
        rx="2.5"
        fill="none"
        stroke={sayfa}
        strokeWidth="1.8"
      />
      <path d="M8 8.5h8M8 12.5h8M8 16.5h4" stroke={sayfa} strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="20" cy="19.5" r="5.6" fill={muhur} />
      <path
        d="M17.6 19.6l1.6 1.7 3.2-3.4"
        fill="none"
        stroke={tik}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
