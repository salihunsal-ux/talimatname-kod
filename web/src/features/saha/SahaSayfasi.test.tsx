import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { calistirmaGorunumu, type CalistirmaGorunumu } from '../../api/calistirma';
import { gununCalistirmalari } from '../../api/planlar';
import { senkManifesti, surumDetayi } from '../../api/saha';
import { SahaSayfasi } from './SahaSayfasi';

vi.mock('../../api/calistirma');
vi.mock('../../api/planlar');
vi.mock('../../api/saha');

const gorunum = vi.mocked(calistirmaGorunumu);
const bugun = vi.mocked(gununCalistirmalari);
const manifest = vi.mocked(senkManifesti);
const surum = vi.mocked(surumDetayi);

function madde(ek: Record<string, unknown>) {
  return {
    item_id: 'm-1',
    title: 'Madde',
    type: 'confirm',
    type_label: 'Onay',
    required: true,
    photo_required: false,
    critical: false,
    min_value: null,
    max_value: null,
    unit: null,
    answer: null,
    ...ek,
  };
}

const CALISTIRMA = {
  run_id: 'r-1',
  branch_id: 'b-1',
  branch_name: 'Kadıköy',
  region_name: 'Anadolu',
  business_day: '2026-11-05',
  status: 'scheduled',
  result: null,
  score_percent: null,
  window_start: '2026-11-05T19:00:00Z',
  window_end: '2026-11-05T22:30:00Z',
  tolerance_end: '2026-11-05T23:30:00Z',
  submitted_at: null,
  template_name: 'Kapanış (kafe)',
  locked_by: null,
  blockers: [],
  sections: [
    {
      id: 's-1',
      title: 'Güvenlik',
      items: [
        madde({ item_id: 'm-1', title: 'Gaz vanası kapatıldı', critical: true }),
        madde({ item_id: 'm-2', title: 'Tezgâh silindi', critical: false }),
      ],
    },
  ],
} as unknown as CalistirmaGorunumu;

function kur() {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={istemci}>
      <SahaSayfasi />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  bugun.mockResolvedValue([
    {
      id: 'r-1',
      branch_name: 'Kadıköy',
      status: 'scheduled',
      window_start: '2026-11-05T19:00:00Z',
      window_end: '2026-11-05T22:30:00Z',
      tolerance_end: '2026-11-05T23:30:00Z',
    },
  ] as never);
  gorunum.mockResolvedValue(CALISTIRMA);
  manifest.mockResolvedValue({ runs: [], template_versions: [] } as never);
  surum.mockResolvedValue({ sections: [] } as never);
});

describe('Saha istemcisi', () => {
  it('kritik maddede “Yapılamadı” düğmesi yok (FR-0804)', async () => {
    kur();
    await userEvent.click(await screen.findByRole('button', { name: 'Listeyi aç' }));

    // Madde atlanamaz: düğme gizlenmiyor, hiç çizilmiyor. Listede iki
    // madde var ve yalnızca kritik olmayanda düğme bulunmalı.
    expect(await screen.findByText('Gaz vanası kapatıldı')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Yapılamadı' })).toHaveLength(1);
    expect(screen.getByText(/Kritik madde atlanamaz/)).toBeInTheDocument();
  });

  it('neyin eksik olduğunu ekranda sayıyor', async () => {
    // Eksikler belgede değil ekranda: bu istemciyi gören herkes
    // neyin olmadığını da görsün.
    kur();

    const katlanir = await screen.findByText(/Bu istemcide olmayanlar/);
    expect(katlanir).toHaveTextContent('(13)');

    await userEvent.click(katlanir);
    expect(screen.getByText(/Tarayıcı yapamıyor/)).toBeInTheDocument();
    expect(screen.getByText('FR-0604')).toBeInTheDocument();
  });

  it('demo olduğunu ve fotoğrafın galeri bayraklı yazıldığını söylüyor', async () => {
    kur();

    expect(await screen.findByText(/Pilot istemcisi değildir/)).toBeInTheDocument();
    expect(screen.getByText(/galeri bayrağıyla kaydedilir/)).toBeInTheDocument();
  });
});
