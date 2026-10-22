import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { subeAgaci, subeDetayi, subeEkle } from '../../api/subeler';
import { SubelerSayfasi } from './SubelerSayfasi';

vi.mock('../../api/subeler');
const agac = vi.mocked(subeAgaci);
const detay = vi.mocked(subeDetayi);
const ekle = vi.mocked(subeEkle);

const KADIKOY = {
  id: 'k-1',
  code: 'KDK',
  name: 'Kadıköy',
  status: 'active' as const,
  region_id: 'r-1',
  timezone: 'Europe/Istanbul',
  open_days: 7,
};

function kur() {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={istemci}>
      <SubelerSayfasi />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  agac.mockResolvedValue([{ id: 'r-1', name: 'Anadolu', branches: [KADIKOY] }]);
});

describe('Şubeler sayfası', () => {
  it('bölge başlığı ve şube sayısı listelenir', async () => {
    kur();
    expect(await screen.findByText('Anadolu · 1')).toBeInTheDocument();
    expect(screen.getByText('Kadıköy')).toBeInTheDocument();
    expect(screen.getByText('KDK')).toBeInTheDocument();
  });

  it('şube seçilince çalışma saatleri ve istasyonlar gösterilir', async () => {
    detay.mockResolvedValue({
      ...KADIKOY,
      address: 'Kadıköy, İstanbul',
      business_hours: [
        { weekday: 0, weekday_name: 'Pazartesi', open_time: '08:00:00', close_time: '23:00:00' },
        { weekday: 6, weekday_name: 'Pazar', open_time: null, close_time: null },
      ],
      stations: [{ id: 'i-1', name: 'Mutfak', kind: 'kitchen' }],
    });

    kur();
    await userEvent.click(await screen.findByText('Kadıköy'));

    expect(await screen.findByText('08:00 – 23:00')).toBeInTheDocument();
    expect(screen.getByText('Kapalı')).toBeInTheDocument();
    expect(screen.getByText('Mutfak')).toBeInTheDocument();
  });

  it('kod çakışmasında sunucunun problem gövdesi gösterilir', async () => {
    ekle.mockRejectedValue({
      type: 'urn:talimatname:sube-kodu-kullanimda',
      title: 'Bu şube kodu zaten var',
      status: 409,
    });

    kur();
    await userEvent.type(await screen.findByLabelText('Kod'), 'KDK');
    await userEvent.type(screen.getByLabelText('Ad'), 'Kadıköy 2');
    await userEvent.click(screen.getByRole('button', { name: 'Şube ekle' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Bu şube kodu zaten var');
  });
});
