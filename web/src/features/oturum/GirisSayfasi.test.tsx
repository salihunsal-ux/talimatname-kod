import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { kodDogrula, kodIste } from '../../api/oturum';
import { GirisSayfasi } from './GirisSayfasi';

vi.mock('../../api/oturum');
const iste = vi.mocked(kodIste);
const dogrula = vi.mocked(kodDogrula);

const KOD_YANITI = {
  phone: '+905321110001',
  delivered: false,
  note: 'SMS sağlayıcısı bağlanınca kod telefona gidecek (ST-067).',
  dev_code: '123456',
};

beforeEach(() => {
  iste.mockReset();
  dogrula.mockReset();
});

async function telefonAdimi() {
  const kullanici = userEvent.setup();
  await kullanici.type(screen.getByLabelText('Telefon numarası'), '05321110001');
  await kullanici.click(screen.getByRole('button', { name: 'Kod iste' }));
  return kullanici;
}

describe('GirisSayfasi', () => {
  it('kod istendiğinde "gönderildi" demez, sebebini söyler', async () => {
    iste.mockResolvedValue(KOD_YANITI);
    render(<GirisSayfasi onGiris={vi.fn()} />);

    await telefonAdimi();

    const uyari = await screen.findByRole('status');
    expect(uyari).toHaveTextContent('kod telefona gönderilmedi');
    expect(uyari.textContent).not.toMatch(/gönderildi(?!\W*değil)/i);
    expect(uyari).toHaveTextContent('Giriş kodu: 123456');
  });

  it('sağlayıcı bağlandığında uyarı kaybolur', async () => {
    iste.mockResolvedValue({ ...KOD_YANITI, delivered: true, dev_code: null });
    render(<GirisSayfasi onGiris={vi.fn()} />);

    await telefonAdimi();

    expect(await screen.findByLabelText('Doğrulama kodu')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('doğru kod girilince oturum açılır', async () => {
    iste.mockResolvedValue(KOD_YANITI);
    dogrula.mockResolvedValue({
      access_token: 'belirtec',
      token_type: 'bearer',
      expires_in_minutes: 30,
      user: { id: 'k1', full_name: 'Cem Yönetici', phone: '+905321110001', roles: [] },
    });
    const onGiris = vi.fn();
    render(<GirisSayfasi onGiris={onGiris} />);

    const kullanici = await telefonAdimi();
    await kullanici.type(await screen.findByLabelText('Doğrulama kodu'), '123456');
    await kullanici.click(screen.getByRole('button', { name: 'Giriş yap' }));

    expect(dogrula).toHaveBeenCalledWith('05321110001', '123456');
    expect(onGiris).toHaveBeenCalled();
  });

  it('hatalı kodda sunucunun gerekçesi gösterilir', async () => {
    iste.mockResolvedValue(KOD_YANITI);
    dogrula.mockRejectedValue({
      type: 'urn:talimatname:kod-gecersiz',
      title: 'Kod doğrulanamadı',
      status: 403,
      detail: 'Kod hatalı (2 hakkınız kaldı)',
    });
    render(<GirisSayfasi onGiris={vi.fn()} />);

    const kullanici = await telefonAdimi();
    await kullanici.type(await screen.findByLabelText('Doğrulama kodu'), '000000');
    await kullanici.click(screen.getByRole('button', { name: 'Giriş yap' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('2 hakkınız kaldı');
  });

  it('bilinmeyen numarada kod adımına geçilmez', async () => {
    iste.mockRejectedValue({
      type: 'urn:talimatname:kullanici-bulunamadi',
      title: 'Bu numarayla kayıtlı kullanıcı yok',
      status: 404,
    });
    render(<GirisSayfasi onGiris={vi.fn()} />);

    await telefonAdimi();

    expect(await screen.findByRole('alert')).toHaveTextContent('kayıtlı kullanıcı yok');
    expect(screen.queryByLabelText('Doğrulama kodu')).not.toBeInTheDocument();
  });

  it('teşhis detayı başlığın yerine geçmiyor (bağımsız test turu B08)', async () => {
    // Eski sürüm `detail ?? title` yazıyordu: ekranda yalnızca
    // "Telefon: +90…" görünüyor, ne olduğu hiç yazmıyordu.
    iste.mockRejectedValue({
      type: 'urn:talimatname:kullanici-bulunamadi',
      title: 'Bu numarayla kayıtlı kullanıcı yok',
      status: 404,
      detail: 'Telefon: +905321110003',
    });
    render(<GirisSayfasi onGiris={vi.fn()} />);

    await telefonAdimi();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Bu numarayla kayıtlı kullanıcı yok',
    );
  });

  it('yanıt gövdesi boş gelse de ekran beyaz kalmaz', async () => {
    /* Ara sunucunun HTML 500'ünde openapi-fetch hem `data` hem
       `error` boş bırakıyordu: `bilgi` tanımsız kalıp giriş ekranı
       çöküyordu (tarayıcıda görüldü). İstemci artık böyle yanıtı
       problem gövdesine çeviriyor; burada en kötü hâli taklit edip
       ekranın ayakta kaldığını sınıyoruz. */
    iste.mockResolvedValue(undefined as never);
    render(<GirisSayfasi onGiris={vi.fn()} />);

    await telefonAdimi();

    expect(screen.getByRole('heading', { name: 'Giriş yap' })).toBeInTheDocument();
  });
});
