import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { panoGetir, type PanoYaniti } from '../../api/pano';
import { PanoSayfasi } from './PanoSayfasi';

vi.mock('../../api/pano');
const getir = vi.mocked(panoGetir);

const HUCRE = {
  plan_id: 'p-1',
  run_id: 'r-1',
  window_start: '2026-11-02T19:00:00Z',
  window_end: '2026-11-02T22:30:00Z',
};

const PANO: PanoYaniti = {
  business_day: '2026-11-02',
  escalation_gaps: [],
  plans: [{ id: 'p-1', name: 'Günlük kapanış' }],
  rows: [
    {
      branch_id: 'b-1',
      branch_name: 'Kadıköy',
      region_name: 'Anadolu',
      cells: [{ ...HUCRE, status: 'submitted', late: false, result: 'passed', exception: false }],
      exception: false,
    },
    {
      branch_id: 'b-2',
      branch_name: 'Üsküdar',
      region_name: 'Anadolu',
      cells: [{ ...HUCRE, status: 'submitted', late: true, result: 'failed', exception: true }],
      exception: true,
    },
  ],
  exception_row_count: 1,
  kpi: {
    total: 2,
    submitted: 2,
    late: 1,
    missed: 0,
    open_now: 0,
    completion_percent: 100,
    all_clear: false,
  },
};

function kur() {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={istemci}>
      <PanoSayfasi />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  getir.mockResolvedValue(PANO);
});

describe('Pano', () => {
  it('varsayılan görünüm yalnızca sorunlu satırları gösterir', async () => {
    kur();
    expect(await screen.findByText(/Üsküdar/)).toBeInTheDocument();
    expect(screen.queryByText(/Kadıköy/)).not.toBeInTheDocument();
  });

  it('tümünü göster sorunsuz satırları da açar ve ikinci istek atmaz', async () => {
    kur();
    await screen.findByText(/Üsküdar/);
    expect(getir).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole('button', { name: /Tümünü göster/ }));

    expect(screen.getByText(/Kadıköy/)).toBeInTheDocument();
    expect(getir).toHaveBeenCalledTimes(1); // süzgeç istemcide
  });

  it('hiçbir şey seçili değilken detay yuvası ne yapılacağını söyler', async () => {
    // Izgaranın altındaki boşluk "sayfa bitti" gibi okunuyordu.
    kur();
    await screen.findByText(/Üsküdar/);

    expect(screen.getByText(/maddeleri, cevapları ve kanıtları burada açılır/)).toBeInTheDocument();
  });

  it('tıklanan hücre seçili işaretlenir', async () => {
    // Satır vurgusu da bu ARIA durumundan türüyor (bilesenler.css);
    // ikinci bir bayrak tutulsaydı ikisi ayrışabilirdi.
    kur();
    const hucre = await screen.findByRole('button', { name: /Başarısız/ });
    expect(hucre).toHaveAttribute('aria-pressed', 'false');

    await userEvent.click(hucre);

    expect(hucre).toHaveAttribute('aria-pressed', 'true');
  });

  it('göstergeler sayılarla gelir', async () => {
    kur();
    expect(await screen.findByText('%100')).toBeInTheDocument();
    expect(screen.getByText('Geç').nextSibling).toHaveTextContent('1');
  });

  it('sorun yoksa ve gün bittiyse "her şey yolunda" der', async () => {
    getir.mockResolvedValue({
      ...PANO,
      rows: [{ ...PANO.rows[0] }],
      exception_row_count: 0,
      kpi: { ...PANO.kpi, late: 0, missed: 0, open_now: 0, all_clear: true },
    });

    kur();
    expect(await screen.findByText('Her şey yolunda')).toBeInTheDocument();
  });

  it('pencereler hâlâ açıkken "her şey yolunda" demez', async () => {
    getir.mockResolvedValue({
      ...PANO,
      rows: [{ ...PANO.rows[0] }],
      exception_row_count: 0,
      kpi: { ...PANO.kpi, late: 0, missed: 0, open_now: 3, all_clear: false },
    });

    kur();
    expect(await screen.findByText('Şimdilik sorun yok')).toBeInTheDocument();
    expect(screen.queryByText('Her şey yolunda')).not.toBeInTheDocument();
    expect(screen.getByText(/3 liste penceresi/)).toBeInTheDocument();
  });

  it('iş günü değişince yeni veri istenir', async () => {
    kur();
    await screen.findByText(/Üsküdar/);

    await userEvent.clear(screen.getByLabelText('İş günü'));
    await userEvent.type(screen.getByLabelText('İş günü'), '2026-11-01');

    expect(getir).toHaveBeenCalledWith('2026-11-01');
  });

  it('gece yarısını aşan pencereyi günüyle yazar', async () => {
    /* "00:00–03:30", iş günü 2 Kasım olan satırda sabah geçmiş gibi
       okunuyordu; oysa pencere o gecenin sonunda açılıyor. PDF bunu
       iki tarihle yazıyordu, ızgara yazmıyordu. */
    getir.mockResolvedValue({
      ...PANO,
      rows: [
        {
          branch_id: 'b-9',
          branch_name: 'Beşiktaş',
          region_name: 'Avrupa',
          cells: [
            {
              plan_id: 'p-1',
              run_id: 'r-9',
              window_start: '2026-11-02T21:00:00Z',
              window_end: '2026-11-03T00:30:00Z',
              status: 'scheduled' as const,
              late: false,
              result: null,
              exception: true,
            },
          ],
          exception: true,
        },
      ],
    });

    kur();

    const hucre = await screen.findByRole('button', { name: /Planlı/ });
    expect(hucre.getAttribute('title')).toMatch(/03[./]11/);
  });
});

describe('eskalasyon boşlukları (BR-11 · FR-0915)', () => {
  // Atlanan basamak yalnızca sunucu günlüğüne yazılıyordu: demoda dört
  // şube müdürsüzdü ve kimse bilmiyordu.

  function boslukla(bosluklar: PanoYaniti['escalation_gaps']) {
    getir.mockResolvedValue({ ...PANO, escalation_gaps: bosluklar });
  }

  it('müdürsüz şubeyi ve uyarının kime gittiğini yazıyor', async () => {
    boslukla([
      {
        branch_id: 'b-9',
        branch_code: 'SSL',
        branch_name: 'Şişli',
        missing: ['Şube müdürü', 'Bölge müdürü'],
        reached: 'admin',
        reached_label: 'Yönetici',
        critical: false,
      },
    ]);

    kur();

    expect(await screen.findByText(/1 şubede uyarı şube müdürüne ulaşmıyor/)).toBeInTheDocument();
    // Yönelme eki: "yönetici gidiyor" değil, "yöneticiye gidiyor".
    expect(
      screen.getByText('Şişli: Şube müdürü ve Bölge müdürü yok — uyarı yöneticiye gidiyor.'),
    ).toBeInTheDocument();
  });

  it('zincirde kimse yoksa bunu ayrıca söylüyor', async () => {
    boslukla([
      {
        branch_id: 'b-9',
        branch_code: 'ZTB',
        branch_name: 'Zeytinburnu',
        missing: ['Şube müdürü', 'Bölge müdürü', 'Yönetici'],
        reached: 'hicbiri',
        reached_label: 'Hiç kimse',
        critical: true,
      },
    ]);

    kur();

    expect(await screen.findByText(/hiç kimseye ulaşmıyor/)).toBeInTheDocument();
    expect(screen.getByText(/uyarı kayboluyor/)).toBeInTheDocument();
  });

  it('boşluk yoksa şerit çıkmıyor', async () => {
    kur();
    await screen.findByText(/Günlük kapanış/);

    expect(screen.queryByText(/ulaşmıyor/)).not.toBeInTheDocument();
  });
});
