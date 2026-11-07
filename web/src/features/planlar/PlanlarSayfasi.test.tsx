import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gununCalistirmalari, planListesi, planOnizleme } from '../../api/planlar';
import { sablonListesi } from '../../api/sablonlar';
import { subeAgaci } from '../../api/subeler';
import { Oturumlu } from '../../test/oturum';
import { PlanlarSayfasi } from './PlanlarSayfasi';

vi.mock('../../api/planlar');
vi.mock('../../api/sablonlar');
vi.mock('../../api/subeler');

const planlar = vi.mocked(planListesi);
const calistirmalar = vi.mocked(gununCalistirmalari);
const onizleme = vi.mocked(planOnizleme);
const sablonlar = vi.mocked(sablonListesi);
const subeler = vi.mocked(subeAgaci);

function kur() {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={istemci}>
      <Oturumlu>
        <PlanlarSayfasi />
      </Oturumlu>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  planlar.mockResolvedValue([
    {
      id: 'p-1',
      name: 'Günlük kapanış',
      template_version_id: 'v-1',
      template_name: 'Kapanış (kafe)',
      branch_ids: ['b-1'],
      branch_count: 3,
      active: true,
      assignment: { kind: 'anyone', role: null, user_id: null },
      recurrence: 'FREQ=DAILY',
      duration_minutes: 210,
      tolerance_minutes: 0,
    },
  ]);
  calistirmalar.mockResolvedValue([
    {
      id: 'r-1',
      plan_id: 'p-1',
      plan_name: 'Günlük kapanış',
      branch_id: 'b-1',
      branch_name: 'Kadıköy',
      business_day: '2026-11-02',
      window_start: '2026-11-02T19:00:00Z',
      writable_from: '2026-11-02T18:45:00Z',
      window_end: '2026-11-02T22:30:00Z',
      tolerance_end: '2026-11-02T22:30:00Z',
      status: 'missed',
      late: false,
    },
  ]);
  sablonlar.mockResolvedValue([
    {
      id: 't-1',
      name: 'Kapanış (kafe)',
      category: null,
      versions: [
        {
          id: 'v-1',
          version_no: 1,
          status: 'published',
          published_at: '2026-10-01T07:00:00Z',
          scored_item_count: 7,
          critical_item_count: 2,
          photo_item_count: 2,
        },
        {
          id: 'v-2',
          version_no: 2,
          status: 'draft',
          published_at: null,
          scored_item_count: 7,
          critical_item_count: 2,
          photo_item_count: 2,
        },
      ],
    },
  ]);
  subeler.mockResolvedValue([
    {
      id: 'reg-1',
      name: 'Anadolu',
      branches: [
        {
          id: 'b-1',
          code: 'KDK',
          name: 'Kadıköy',
          status: 'active',
          region_id: 'reg-1',
          timezone: 'Europe/Istanbul',
          open_days: 7,
        },
      ],
    },
  ]);
});

describe('Planlar sayfası', () => {
  it('plan satırı ve bugünün çalıştırmaları durumuyla listelenir', async () => {
    kur();
    expect(await screen.findByText('Günlük kapanış')).toBeInTheDocument();
    expect(screen.getByText('3 şube')).toBeInTheDocument();
    expect(await screen.findByText('Kaçırıldı')).toBeInTheDocument();
  });

  it('tekrar kuralı çiğ RFC metni olarak değil okunur hâlde yazılır', async () => {
    // Şube müdürü "FREQ=DAILY" okuyordu.
    kur();
    expect(await screen.findByText('Her gün')).toBeInTheDocument();
    expect(screen.queryByText(/FREQ=/)).not.toBeInTheDocument();
  });

  it('plan formu alan gruplarına ayrılmıştır', async () => {
    // Yirmiden çok alan tek bir sarmalanan satırdaydı: koşullu alanlar
    // göründükçe sıra yeniden akıyordu. Grup aynı zamanda ekran
    // okuyucuda duyurulan bir sınır.
    kur();
    await screen.findByText('Günlük kapanış');

    expect(screen.getByRole('group', { name: 'Ne yapılacak' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Ne zaman' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Pencere ve tolerans' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Kapsam (şubeler)' })).toBeInTheDocument();
  });

  it('eksik alanla önizleme yapılamaz', async () => {
    kur();
    await screen.findByText('Günlük kapanış');
    expect(screen.getByRole('button', { name: '7 gün önizle' })).toBeDisabled();
    expect(onizleme).not.toHaveBeenCalled();
  });

  it('yalnızca yayınlanmış sürümler plana bağlanabilir', async () => {
    kur();
    await screen.findByText('Günlük kapanış');
    const secenekler = [...screen.getByLabelText('Şablon').querySelectorAll('option')].map(
      (o) => o.textContent,
    );
    expect(secenekler).toContain('Kapanış (kafe) · Sürüm 1');
    expect(secenekler).not.toContain('Kapanış (kafe) · Sürüm 2');
  });

  it('form dolunca önizleme sunucudan alınır ve listelenir', async () => {
    onizleme.mockResolvedValue({
      days: 7,
      run_count: 1,
      runs: [
        {
          id: 'r-2',
          plan_id: 'p-x',
          plan_name: 'Günlük kapanış',
          branch_id: 'b-1',
          branch_name: 'Kadıköy',
          business_day: '2026-11-02',
          window_start: '2026-11-02T11:00:00Z',
          writable_from: '2026-11-02T10:45:00Z',
          window_end: '2026-11-02T14:00:00Z',
          tolerance_end: '2026-11-02T18:00:00Z',
          status: 'scheduled',
          late: false,
        },
      ],
    });

    kur();
    await screen.findByText('Günlük kapanış');
    await userEvent.type(screen.getByLabelText('Plan adı'), 'Haftalık derin temizlik');
    await userEvent.selectOptions(screen.getByLabelText('Şablon'), 'v-1');
    await userEvent.click(screen.getByLabelText('Kadıköy'));
    await userEvent.click(screen.getByRole('button', { name: '7 gün önizle' }));

    expect(await screen.findByText(/Önizleme \(7 gün\): 1 çalıştırma/)).toBeInTheDocument();
    expect(onizleme).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Haftalık derin temizlik', branch_ids: ['b-1'] }),
    );
  });

  it('haftalık seçilince gün çipleri çıkar', async () => {
    kur();
    await screen.findByText('Günlük kapanış');
    expect(screen.queryByLabelText('Pzt')).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Tekrar'), 'weekly');
    expect(screen.getByLabelText('Pzt')).toBeInTheDocument();
  });
});
