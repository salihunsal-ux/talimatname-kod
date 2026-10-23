import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  aksiyonKapat,
  aksiyonListesi,
  aksiyonSayaclari,
  type AksiyonOzet,
} from '../../api/aksiyonlar';
import { subeAgaci } from '../../api/subeler';
import { AksiyonlarSayfasi } from './AksiyonlarSayfasi';

vi.mock('../../api/aksiyonlar');
vi.mock('../../api/subeler');

const liste = vi.mocked(aksiyonListesi);
const sayac = vi.mocked(aksiyonSayaclari);
const kapat = vi.mocked(aksiyonKapat);
const subeler = vi.mocked(subeAgaci);

const KACIRILAN: AksiyonOzet = {
  id: 'a-1',
  branch_id: 'b-1',
  branch_name: 'Beşiktaş',
  title: 'Günlük kapanış yapılmadı (2026-11-02)',
  description: 'Liste penceresi ve tolerans süresi içinde tamamlanmadı.',
  source: 'missed_run',
  source_label: 'Kaçırılan liste',
  priority: 'high',
  priority_label: 'Yüksek',
  status: 'open',
  opened_at: '2026-11-03T06:00:00Z',
  due_at: '2026-11-04T06:00:00Z',
  overdue: false,
  remaining_hours: 20,
  closed_at: null,
  close_note: null,
};

function kur() {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={istemci}>
      <AksiyonlarSayfasi />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  liste.mockResolvedValue([KACIRILAN]);
  sayac.mockResolvedValue({ open: 1, overdue: 0, critical: 0 });
  subeler.mockResolvedValue([
    {
      id: 'r-1',
      name: 'Avrupa',
      branches: [
        {
          id: 'b-1',
          code: 'BSK',
          name: 'Beşiktaş',
          status: 'active',
          region_id: 'r-1',
          timezone: 'Europe/Istanbul',
          open_days: 7,
        },
      ],
    },
  ]);
});

describe('Aksiyonlar sayfası', () => {
  it('kaynak, öncelik ve kalan süre gösterilir', async () => {
    kur();
    const baslik = await screen.findByText(/Günlük kapanış yapılmadı/);
    // "Yüksek" hem kartta hem öncelik seçeneklerinde geçiyor: kartı ara.
    const kart = baslik.closest('li');
    expect(kart).toHaveTextContent('Yüksek');
    expect(kart).toHaveTextContent('Kaçırılan liste');
    expect(kart).toHaveTextContent('20 saat kaldı');
  });

  it('gecikmiş aksiyon geçen süreyi gösterir', async () => {
    liste.mockResolvedValue([{ ...KACIRILAN, overdue: true, remaining_hours: -5 }]);
    kur();
    expect(await screen.findByText('5 saat gecikti')).toBeInTheDocument();
  });

  it('kapatma notsuz gönderilemez: alan açılır, sunucuya gidilmez', async () => {
    kur();
    await screen.findByText(/Günlük kapanış yapılmadı/);

    await userEvent.click(screen.getByRole('button', { name: 'Kapat' }));

    expect(screen.getByLabelText('Kapanış notu')).toBeInTheDocument();
    expect(kapat).not.toHaveBeenCalled();
  });

  it('not yazılınca kapatma sunucuya gider', async () => {
    kapat.mockResolvedValue({
      ...KACIRILAN,
      status: 'closed',
      close_note: 'Telafi listesi açıldı',
    });
    kur();
    await screen.findByText(/Günlük kapanış yapılmadı/);

    await userEvent.click(screen.getByRole('button', { name: 'Kapat' }));
    await userEvent.type(screen.getByLabelText('Kapanış notu'), 'Telafi listesi açıldı');
    await userEvent.click(screen.getAllByRole('button', { name: 'Kapat' })[0]);

    expect(kapat).toHaveBeenCalledWith('a-1', 'Telafi listesi açıldı');
  });

  it('kapalı aksiyonda kapanış notu görünür, kapat düğmesi görünmez', async () => {
    liste.mockResolvedValue([
      {
        ...KACIRILAN,
        status: 'closed',
        remaining_hours: null,
        closed_at: '2026-11-03T08:00:00Z',
        close_note: 'Telafi listesi açıldı',
      },
    ]);

    kur();
    expect(await screen.findByText(/Telafi listesi açıldı/)).toBeInTheDocument();
    expect(screen.getByText('Kapandı')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Kapat' })).not.toBeInTheDocument();
  });

  it('vade kuralı ekranda yazılı', async () => {
    kur();
    expect(
      await screen.findByText(/kritik 4 saat, yüksek 24 saat, normal 72 saat/),
    ).toBeInTheDocument();
  });
});
