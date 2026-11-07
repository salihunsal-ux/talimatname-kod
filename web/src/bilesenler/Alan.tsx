import type { InputHTMLAttributes, ReactNode } from 'react';

/**
 * Etiketli giriş alanı. Etiket `htmlFor` ile bağlı, ipucu ve hata
 * `aria-describedby` ile: ekran okuyucu üçünü de okur (NFR-11).
 *
 * `hata` verildiğinde alan `aria-invalid` oluyor ve cümle alanın altına
 * iliştiriliyor. Öncesinde sunucunun reddi yalnızca formun dibindeki
 * ortak kutuda duruyordu: ekran okuyucu "Bu şube kodu zaten var" diyor
 * ama hangi alan olduğunu söylemiyordu (bağımsız test turu D-4).
 */
export function Alan({
  id,
  etiket,
  ipucu,
  hata,
  className,
  ...kalan
}: InputHTMLAttributes<HTMLInputElement> & {
  id: string;
  etiket: ReactNode;
  ipucu?: ReactNode;
  /** Bu alana ait hata cümlesi; verilirse alan geçersiz işaretlenir. */
  hata?: ReactNode;
}) {
  const ipucuId = ipucu != null ? `${id}-ipucu` : undefined;
  const hataId = hata != null ? `${id}-hata` : undefined;
  const tarif = [hataId, ipucuId].filter(Boolean).join(' ') || undefined;

  return (
    <div className="alan-sarmal">
      <label className="alan-etiket" htmlFor={id}>
        {etiket}
      </label>
      <input
        id={id}
        className={['alan', className ?? ''].filter(Boolean).join(' ')}
        aria-describedby={tarif}
        aria-invalid={hata != null || undefined}
        {...kalan}
      />
      {hata != null && (
        <span className="alan-hatasi" id={hataId}>
          {hata}
        </span>
      )}
      {ipucu != null && (
        <span className="alan-ipucu" id={ipucuId}>
          {ipucu}
        </span>
      )}
    </div>
  );
}
