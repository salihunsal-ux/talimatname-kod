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
  writable_from: '2026-11-05T18:45:00Z',
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
      writable_from: '2026-11-05T18:45:00Z',
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

describe('pencere kapısı ve ilerleme (bağımsız test turu Y-1, O-3)', () => {
  /** Listeyi, penceresi verilen anda açılacak biçimde kurar. */
  function pencere(acilis: Date, bitis: Date) {
    bugun.mockResolvedValue([
      {
        id: 'r-1',
        branch_name: 'Kadıköy',
        status: 'scheduled',
        window_start: acilis.toISOString(),
        writable_from: acilis.toISOString(),
        window_end: bitis.toISOString(),
        tolerance_end: new Date(bitis.getTime() + 3_600_000).toISOString(),
      },
    ] as never);
    gorunum.mockResolvedValue({
      ...CALISTIRMA,
      window_start: acilis.toISOString(),
      writable_from: acilis.toISOString(),
      window_end: bitis.toISOString(),
      tolerance_end: new Date(bitis.getTime() + 3_600_000).toISOString(),
    } as unknown as CalistirmaGorunumu);
  }

  it('penceresi açılmamış listeyi doldurmaya davet etmiyor', async () => {
    // Kapanış listesi gece açılacak; öğlen "Listeyi aç" demek
    // doldurulamayacak bir işe çağırmaktı (sunucu `pencere-acilmadi`).
    const sonra = new Date(Date.now() + 6 * 3_600_000);
    pencere(sonra, new Date(sonra.getTime() + 3_600_000));
    kur();

    expect(await screen.findByRole('button', { name: 'Listeyi gör' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Listeyi aç' })).not.toBeInTheDocument();
  });

  it('açılmamış liste okunur ama cevap düğmeleri kilitli', async () => {
    const sonra = new Date(Date.now() + 6 * 3_600_000);
    pencere(sonra, new Date(sonra.getTime() + 3_600_000));
    kur();
    await userEvent.click(await screen.findByRole('button', { name: 'Listeyi gör' }));

    expect(await screen.findByText(/Pencere henüz açılmadı/)).toBeInTheDocument();
    expect(screen.getByText('Tezgâh silindi')).toBeInTheDocument();
  });

  it('penceresi açık listeyi doldurmaya çağırıyor', async () => {
    const once = new Date(Date.now() - 10 * 60_000);
    pencere(once, new Date(Date.now() + 3_600_000));
    kur();

    expect(await screen.findByRole('button', { name: 'Listeyi aç' })).toBeInTheDocument();
  });

  it('ilerleme sayacı talimat satırını saymıyor', async () => {
    // Dokunulmamış listede "1/8" yazıyordu: talimat satırı hem paya hem
    // paydaya giriyordu. Doğrusu "0/2" (iki cevaplanır madde).
    const once = new Date(Date.now() - 10 * 60_000);
    pencere(once, new Date(Date.now() + 3_600_000));
    gorunum.mockResolvedValue({
      ...CALISTIRMA,
      window_start: once.toISOString(),
      writable_from: once.toISOString(),
      window_end: new Date(Date.now() + 3_600_000).toISOString(),
      tolerance_end: new Date(Date.now() + 7_200_000).toISOString(),
      sections: [
        {
          id: 's-1',
          title: 'Güvenlik',
          items: [
            madde({ item_id: 'm-0', title: 'Sıra: mutfak → salon', type: 'instruction' }),
            madde({ item_id: 'm-1', title: 'Gaz vanası kapatıldı', critical: true }),
            madde({ item_id: 'm-2', title: 'Tezgâh silindi' }),
          ],
        },
      ],
    } as unknown as CalistirmaGorunumu);
    kur();
    await userEvent.click(await screen.findByRole('button', { name: 'Listeyi aç' }));

    expect(await screen.findByText(/0\/2 madde/)).toBeInTheDocument();
    expect(screen.queryByText(/1\/3 madde/)).not.toBeInTheDocument();
  });
});
