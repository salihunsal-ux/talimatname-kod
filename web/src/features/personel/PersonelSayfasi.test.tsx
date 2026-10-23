import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { personelDavet, personelListesi, personelMaskele } from '../../api/personel';
import { subeAgaci } from '../../api/subeler';
import { Oturumlu } from '../../test/oturum';
import { PersonelSayfasi } from './PersonelSayfasi';

vi.mock('../../api/personel');
vi.mock('../../api/subeler');
const liste = vi.mocked(personelListesi);
const davet = vi.mocked(personelDavet);
const maskele = vi.mocked(personelMaskele);
const agac = vi.mocked(subeAgaci);

const AYSE = {
  id: 'u-1',
  full_name: 'Ayşe Şube',
  phone: '+905321110003',
  email: null,
  status: 'active' as const,
  assignments: [
    {
      role: 'branch_manager' as const,
      role_label: 'Şube müdürü',
      scope_type: 'branch' as const,
      scope_id: 'b-1',
    },
  ],
  invited_at: null,
  masked_at: null,
  pin_set: false,
};

function kur() {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={istemci}>
      <Oturumlu>
        <PersonelSayfasi />
      </Oturumlu>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  liste.mockResolvedValue([AYSE]);
  agac.mockResolvedValue([
    {
      id: 'r-1',
      name: 'Anadolu',
      branches: [
        {
          id: 'b-1',
          code: 'KDK',
          name: 'Kadıköy',
          status: 'active',
          region_id: 'r-1',
          timezone: 'Europe/Istanbul',
          open_days: 7,
        },
      ],
    },
  ]);
});

describe('Personel sayfası', () => {
  it('rol ve kapsam şube adıyla gösterilir', async () => {
    kur();
    expect(await screen.findByText('Ayşe Şube')).toBeInTheDocument();
    // "Şube müdürü" hem tabloda hem rol seçeneklerinde geçiyor: satırdaki olanı ara.
    const satir = screen.getByRole('row', { name: /Ayşe Şube/ });
    expect(satir).toHaveTextContent('Şube müdürü');
    expect(await screen.findByText('· Kadıköy')).toBeInTheDocument();
  });

  it('yönetici seçilince kapsam seçicisi gizlenir', async () => {
    kur();
    await screen.findByText('Ayşe Şube');
    const rolSecicileri = screen.getAllByLabelText('Rol');
    // Son seçici davet formundaki rol alanı
    await userEvent.selectOptions(rolSecicileri[rolSecicileri.length - 1], 'admin');
    expect(screen.queryByText('Seçiniz')).not.toBeInTheDocument();
  });

  it('davet gönderildi demez, kuyruğa alındı der', async () => {
    davet.mockResolvedValue({
      user: { ...AYSE, id: 'u-2', full_name: 'Yeni Kişi' },
      invite_sent: false,
      invite_note: 'SMS sağlayıcısı bağlanınca davet gönderilecek (ST-044).',
    });

    kur();
    await screen.findByText('Ayşe Şube');
    await userEvent.type(screen.getByLabelText('Ad soyad'), 'Yeni Kişi');
    await userEvent.type(screen.getByLabelText('Telefon'), '0532 999 11 22');
    await userEvent.selectOptions(screen.getAllByLabelText('Şube')[1], 'b-1');
    await userEvent.click(screen.getByRole('button', { name: 'Davet et' }));

    const bildirim = await screen.findByRole('status');
    expect(bildirim).toHaveTextContent('Davet SMS');
    expect(bildirim).not.toHaveTextContent('gönderildi.');
  });

  it('maskeleme iki adımda onaylanır', async () => {
    maskele.mockResolvedValue({ ...AYSE, status: 'masked', phone: null, assignments: [] });

    kur();
    await screen.findByText('Ayşe Şube');
    await userEvent.click(screen.getByRole('button', { name: 'Maskele' }));

    expect(maskele).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Maskelemeyi onayla' }));
    expect(maskele).toHaveBeenCalledWith('u-1');
  });
});
