import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  aylikOzet,
  aylikOzetPdf,
  dosyayiIndir,
  kanitGalerisi,
  olcumGunlugu,
  olcumGunluguPdf,
  type AylikOzet,
  type OlcumSerisi,
} from '../../api/raporlar';
import { RaporlarSayfasi } from './RaporlarSayfasi';

vi.mock('../../api/raporlar');
vi.mock('../../api/kanitlar');
const ozetGetir = vi.mocked(aylikOzet);
const olcumGetir = vi.mocked(olcumGunlugu);
const galeriGetir = vi.mocked(kanitGalerisi);
const aylikPdf = vi.mocked(aylikOzetPdf);
const olcumPdf = vi.mocked(olcumGunluguPdf);
const indir = vi.mocked(dosyayiIndir);

const SAYAC = {
  total: 10,
  on_time: 6,
  late: 2,
  missed: 1,
  cancelled: 0,
  open: 1,
  failed: 2,
  not_done_items: 3,
  closed: 9,
  on_time_percent: 67,
};

const OZET: AylikOzet = {
  year: 2026,
  month: 11,
  month_name: 'Kasım',
  first_day: '2026-11-01',
  last_day: '2026-11-30',
  counters: SAYAC,
  branches: [
    {
      branch_id: 'b-2',
      branch_code: 'USK',
      branch_name: 'Üsküdar',
      counters: { ...SAYAC, on_time_percent: 20 },
    },
    {
      branch_id: 'b-1',
      branch_code: 'KDK',
      branch_name: 'Kadıköy',
      counters: { ...SAYAC, on_time_percent: 90 },
    },
  ],
};

const SERI: OlcumSerisi = {
  item_id: 'i-1',
  item_title: 'Süt dolabı sıcaklığı',
  unit: '°C',
  min_value: 0,
  max_value: 4,
  out_of_range_count: 1,
  points: [
    {
      run_id: 'r-1',
      branch_id: 'b-1',
      measured_at: '2026-11-02T20:00:00Z',
      value: 3,
      out_of_range: false,
    },
    {
      run_id: 'r-2',
      branch_id: 'b-1',
      measured_at: '2026-11-03T20:00:00Z',
      value: 9,
      out_of_range: true,
    },
  ],
};

function kur() {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={istemci}>
      <RaporlarSayfasi />
    </QueryClientProvider>,
  );
}

describe('RaporlarSayfasi', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    ozetGetir.mockResolvedValue(OZET);
    olcumGetir.mockResolvedValue([SERI]);
    galeriGetir.mockResolvedValue([]);
    aylikPdf.mockResolvedValue(new Blob([new Uint8Array([37, 80, 68, 70])]));
    olcumPdf.mockResolvedValue(new Blob([new Uint8Array([37, 80, 68, 70])]));
  });

  it('aylık özet sayıları ve yüzdeyi gösterir', async () => {
    kur();

    expect(await screen.findByText('%67')).toBeInTheDocument();
    expect(screen.getByText('Şube kırılımı')).toBeInTheDocument();
  });

  it('en kötü şube üstte listelenir', async () => {
    kur();

    const satirlar = await screen.findAllByRole('row');
    // İlk satır başlık; ikincisi en düşük zamanındalık.
    expect(satirlar[1]).toHaveTextContent('Üsküdar');
    expect(satirlar[1]).toHaveTextContent('%20');
  });

  it('ölçülemeyen yüzde sıfır değil "ölçülemedi" yazar', async () => {
    ozetGetir.mockResolvedValue({
      ...OZET,
      counters: { ...SAYAC, closed: 0, on_time_percent: null },
      branches: [
        {
          branch_id: 'b-1',
          branch_code: 'KDK',
          branch_name: 'Kadıköy',
          counters: { ...SAYAC, closed: 0, on_time_percent: null },
        },
      ],
    });
    kur();

    expect(await screen.findByText('—')).toBeInTheDocument();
    expect(screen.getByText('ölçülemedi')).toBeInTheDocument();
  });

  it('ölçüm günlüğü aralık dışını işaretler', async () => {
    kur();

    await userEvent.click(screen.getByRole('tab', { name: 'Ölçüm günlüğü' }));

    expect(await screen.findByText('Süt dolabı sıcaklığı')).toBeInTheDocument();
    expect(screen.getByText('Kabul aralığı 0–4°C')).toBeInTheDocument();
    expect(screen.getByText('1 ölçüm aralık dışı')).toBeInTheDocument();
  });

  it('aralık dışı süzgeci sunucuya gider', async () => {
    kur();

    await userEvent.click(screen.getByRole('tab', { name: 'Ölçüm günlüğü' }));
    await screen.findByText('Süt dolabı sıcaklığı');
    await userEvent.click(screen.getByLabelText('Yalnızca aralık dışı ölçümler'));

    expect(olcumGetir).toHaveBeenLastCalledWith(expect.any(String), expect.any(String), true);
  });

  it('aylık özet PDF olarak indirilir', async () => {
    kur();
    await screen.findByText('%67');

    await userEvent.click(screen.getByRole('button', { name: 'PDF indir' }));

    // Ekranda seçili ay bugünün ayı: beklenti veriden değil takvimden.
    const bugun = new Date();
    expect(aylikPdf).toHaveBeenCalledWith(bugun.getFullYear(), bugun.getMonth() + 1);
    expect(indir).toHaveBeenCalledWith(expect.any(Blob), expect.stringContaining('aylik-ozet.pdf'));
  });

  it('ölçüm günlüğü PDF ekrandaki süzgeci taşır', async () => {
    kur();
    await userEvent.click(screen.getByRole('tab', { name: 'Ölçüm günlüğü' }));
    await screen.findByText('Süt dolabı sıcaklığı');
    await userEvent.click(screen.getByLabelText('Yalnızca aralık dışı ölçümler'));

    await userEvent.click(screen.getByRole('button', { name: 'PDF indir' }));

    // Kâğıt ekranda görünenin aynısı olmalı: süzgeç de gider.
    expect(olcumPdf).toHaveBeenCalledWith(expect.any(String), expect.any(String), true);
  });

  it('PDF üretilemezse hata görünür', async () => {
    aylikPdf.mockRejectedValue(new Error('500'));
    kur();
    await screen.findByText('%67');

    await userEvent.click(screen.getByRole('button', { name: 'PDF indir' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('PDF üretilemedi');
    expect(indir).not.toHaveBeenCalled();
  });

  it('galeri boşken bunu söyler', async () => {
    kur();

    await userEvent.click(screen.getByRole('tab', { name: 'Kanıt galerisi' }));

    expect(await screen.findByText('Bu aralıkta kanıt yok.')).toBeInTheDocument();
  });
});
