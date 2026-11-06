import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Hata } from './Durum';

/** Sunucunun RFC 9457 gövdesi; istemci davranışı `type`a bakar. */
function problem(tip: string, baslik: string, ek: Record<string, unknown> = {}) {
  return { type: `urn:talimatname:${tip}`, title: baslik, status: 403, ...ek };
}

describe('Hata', () => {
  it('sunucu cevap verdiyse onun cümlesini yazıyor', () => {
    // Asıl kusur buydu: oturum süresi dolduğunda ekran "Sunucuya
    // bağlanılamadı" diyordu, oysa sunucu gayet iyi cevap vermişti.
    render(
      <Hata
        hata={problem('belirtec-gecersiz', 'Oturum geçersiz ya da süresi doldu')}
        metin="Sunucuya bağlanılamadı"
      />,
    );

    expect(screen.getByRole('alert')).toHaveTextContent('Oturum geçersiz ya da süresi doldu');
    expect(screen.queryByText('Sunucuya bağlanılamadı')).not.toBeInTheDocument();
  });

  it('kutu yalnızca cümleyi gösteriyor, eylem taşımıyor', () => {
    // Oturum düşüşünü sorgu önbelleği karşılıyor (api/oturum.test.ts):
    // kutunun işi anlatmak, kurtarmak değil.
    render(<Hata hata={problem('gecersiz-istek', 'Bu şube kodu zaten var')} />);

    expect(screen.getByRole('alert')).toHaveTextContent('Bu şube kodu zaten var');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('alan hatasını da yazıyor', () => {
    render(
      <Hata
        hata={problem('gecersiz-istek', 'Girdi doğrulanamadı', {
          errors: [{ alan: 'code', sebep: 'Bu şube kodu zaten var' }],
        })}
      />,
    );

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Girdi doğrulanamadı: Bu şube kodu zaten var',
    );
  });

  it('gövde çözülemediyse yedek metne düşüyor', () => {
    // Gerçek ağ hatası: `fetch` reddedildi, problem gövdesi yok.
    render(<Hata hata={new TypeError('Failed to fetch')} metin="Sunucuya bağlanılamadı" />);

    expect(screen.getByRole('alert')).toHaveTextContent('Sunucuya bağlanılamadı');
  });
});
