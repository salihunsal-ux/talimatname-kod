import type { InputHTMLAttributes, ReactNode } from 'react';

/**
 * Etiketli giriş alanı. Etiket `htmlFor` ile bağlı, ipucu
 * `aria-describedby` ile: ekran okuyucu ikisini de okur (NFR-11).
 */
export function Alan({
  id,
  etiket,
  ipucu,
  className,
  ...kalan
}: InputHTMLAttributes<HTMLInputElement> & { id: string; etiket: ReactNode; ipucu?: ReactNode }) {
  const ipucuId = ipucu != null ? `${id}-ipucu` : undefined;

  return (
    <div className="alan-sarmal">
      <label className="alan-etiket" htmlFor={id}>
        {etiket}
      </label>
      <input
        id={id}
        className={['alan', className ?? ''].filter(Boolean).join(' ')}
        aria-describedby={ipucuId}
        {...kalan}
      />
      {ipucu != null && (
        <span className="alan-ipucu" id={ipucuId}>
          {ipucu}
        </span>
      )}
    </div>
  );
}
