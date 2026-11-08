import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  personelDavet,
  personelDuzelt,
  personelListesi,
  personelMaskele,
} from '../../api/personel';
import { subeAgaci } from '../../api/subeler';
import { Oturumlu } from '../../test/oturum';
import { PersonelSayfasi } from './PersonelSayfasi';

vi.mock('../../api/personel');
vi.mock('../../api/subeler');
const liste = vi.mocked(personelListesi);
const davet = vi.mocked(personelDavet);
const maskele = vi.mocked(personelMaskele);
const duzelt = vi.mocked(personelDuzelt);
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

  it('yanlış yazılmış ad satırın içinde düzeltilir', async () => {
    // Ad yalnızca toplu içe aktarmayla güncellenebiliyordu; isim cevap
    // satırlarında ve imzalı raporlarda göründüğü için satır içinde
    // düzeltilebilmeli.
    liste.mockResolvedValue([{ ...AYSE, full_name: 'Ayse Sube' }]);
    duzelt.mockResolvedValue({ ...AYSE, full_name: 'Ayşe Şube' });

    kur();
    await screen.findByText('Ayse Sube');
    await userEvent.click(screen.getByRole('button', { name: 'Adı düzelt' }));

    const alan = screen.getByLabelText('Adı düzelt');
    expect(alan).toHaveValue('Ayse Sube');
    await userEvent.clear(alan);
    await userEvent.type(alan, 'Ayşe Şube');
    await userEvent.click(screen.getByRole('button', { name: 'Kaydet' }));

    expect(duzelt).toHaveBeenCalledWith('u-1', { full_name: 'Ayşe Şube' });
  });

  it('boş ad kaydedilemez', async () => {
    kur();
    await screen.findByText('Ayşe Şube');
    await userEvent.click(screen.getByRole('button', { name: 'Adı düzelt' }));
    await userEvent.clear(screen.getByLabelText('Adı düzelt'));

    expect(screen.getByRole('button', { name: 'Kaydet' })).toBeDisabled();
  });

  it('vazgeçince ad eski hâline döner, istek gitmez', async () => {
    kur();
    await screen.findByText('Ayşe Şube');
    await userEvent.click(screen.getByRole('button', { name: 'Adı düzelt' }));
    await userEvent.type(screen.getByLabelText('Adı düzelt'), ' yanlış');
    await userEvent.click(screen.getByRole('button', { name: 'Vazgeç' }));

    expect(duzelt).not.toHaveBeenCalled();
    expect(screen.getByRole('row', { name: /Ayşe Şube/ })).toBeInTheDocument();
  });

  it('maskeli kayıtta düzeltme düğmesi çıkmaz', async () => {
    // BR-22: maskeleme geri alınamaz, takma etiket yeniden adlandırılamaz.
    liste.mockResolvedValue([
      { ...AYSE, full_name: 'Eski personel #4821', status: 'masked', phone: null },
    ]);

    kur();
    await screen.findByText('Eski personel #4821');

    expect(screen.queryByRole('button', { name: 'Adı düzelt' })).not.toBeInTheDocument();
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

describe('denetçi rolü', () => {
  it('rol listesinde var ve bölge kapsamı istiyor', async () => {
    // Denetçi şubeye gider ama şubeye bağlı değil: kapsamı bölge.
    kur();
    await screen.findByText('Ayşe Şube');
    const rolSecicileri = screen.getAllByLabelText('Rol');
    const davetRolu = rolSecicileri[rolSecicileri.length - 1];

    await userEvent.selectOptions(davetRolu, 'auditor');

    // Rol seçicileri birden fazla (süzgeç + davet formu): davet
    // formundakine bakıyoruz.
    expect(davetRolu).toHaveValue('auditor');
    expect(screen.getByLabelText('Bölge')).toBeInTheDocument();
  });
});
