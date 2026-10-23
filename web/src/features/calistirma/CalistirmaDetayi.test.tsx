import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { calistirmaGorunumu, type CalistirmaGorunumu } from '../../api/calistirma';
import { CalistirmaDetayi } from './CalistirmaDetayi';

vi.mock('../../api/calistirma');
const getir = vi.mocked(calistirmaGorunumu);

const MADDE = {
  type_label: 'Onay',
  required: true,
  photo_required: false,
  critical: false,
  min_value: null,
  max_value: null,
  unit: null,
};

const GORUNUM: CalistirmaGorunumu = {
  run_id: 'r-1',
  branch_id: 'b-1',
  business_day: '2026-11-02',
  status: 'submitted',
  result: 'failed',
  score_percent: 71,
  window_start: '2026-11-02T19:00:00Z',
  window_end: '2026-11-02T22:30:00Z',
  tolerance_end: '2026-11-02T22:30:00Z',
  submitted_at: '2026-11-02T21:40:00Z',
  template_name: 'Kapanış (kafe)',
  locked_by: null,
  sections: [
    {
      id: 's-1',
      title: 'Mutfak',
      items: [
        {
          ...MADDE,
          item_id: 'i-0',
          title: 'Kapanış sırası',
          type: 'instruction',
          type_label: 'Talimat',
          answer: null,
        },
        {
          ...MADDE,
          item_id: 'i-1',
          title: 'Espresso makinesi geri yıkama',
          type: 'confirm',
          answer: {
            id: 'a-1',
            item_id: 'i-1',
            state: 'passed',
            value: null,
            note: null,
            evidence_count: 0,
            answered_at: '2026-11-02T21:00:00Z',
            clock_skew_minutes: 0,
            clock_flagged: false,
          },
        },
        {
          ...MADDE,
          item_id: 'i-2',
          title: 'Süt dolabı sıcaklığı',
          type: 'temperature',
          type_label: 'Sıcaklık',
          critical: true,
          answer: {
            id: 'a-2',
            item_id: 'i-2',
            state: 'failed',
            value: 9,
            note: 'Sıcaklık 9 derece, teknisyen çağrıldı',
            evidence_count: 1,
            answered_at: '2026-11-02T21:05:00Z',
            clock_skew_minutes: 40,
            clock_flagged: true,
          },
        },
        {
          ...MADDE,
          item_id: 'i-3',
          title: 'Cevapsız madde',
          type: 'confirm',
          answer: null,
        },
      ],
    },
  ],
  blockers: [{ item_id: 'i-3', title: 'Cevapsız madde', kind: 'unanswered' }],
};

function kur(onKapat = vi.fn()) {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={istemci}>
      <CalistirmaDetayi runId="r-1" onKapat={onKapat} />
    </QueryClientProvider>,
  );
  return onKapat;
}

beforeEach(() => {
  vi.resetAllMocks();
  getir.mockResolvedValue(GORUNUM);
});

describe('Çalıştırma detayı', () => {
  it('puan ve sonuç başlıkta gösterilir', async () => {
    kur();
    expect(await screen.findByText('Kapanış (kafe)')).toBeInTheDocument();
    expect(screen.getByText('%71')).toBeInTheDocument();
    expect(screen.getByText('Başarısız')).toBeInTheDocument();
  });

  it('cevap durumları, kanıt sayısı ve not gösterilir', async () => {
    kur();
    await screen.findByText('Kapanış (kafe)');

    expect(screen.getAllByText('Geçti')).toHaveLength(1);
    expect(screen.getByText('Geçmedi')).toBeInTheDocument();
    expect(screen.getByText('Sıcaklık 9 derece, teknisyen çağrıldı')).toBeInTheDocument();
    expect(screen.getByText('Cevapsız')).toBeInTheDocument();
  });

  it('talimat satırı cevap beklemez', async () => {
    kur();
    await screen.findByText('Kapanış (kafe)');
    const satir = screen.getByText('Kapanış sırası').closest('li');
    expect(satir).toHaveTextContent('Talimat');
    expect(satir).not.toHaveTextContent('Cevapsız');
  });

  it('cihaz saati sapması işaretlenir', async () => {
    kur();
    await screen.findByText('Kapanış (kafe)');
    expect(screen.getByText('cihaz saati')).toBeInTheDocument();
  });

  it('gönderime engel eksikler listelenir', async () => {
    kur();
    expect(await screen.findByText(/Gönderime engel eksikler/)).toBeInTheDocument();
    expect(screen.getByText(/cevaplanmadı/)).toBeInTheDocument();
  });

  it('kapat düğmesi geri çağırır', async () => {
    const onKapat = kur();
    await screen.findByText('Kapanış (kafe)');
    await userEvent.click(screen.getByRole('button', { name: 'Kapat' }));
    expect(onKapat).toHaveBeenCalled();
  });
});
