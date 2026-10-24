import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  kurulumDurumu,
  markaKaydet,
  subeOnizle,
  subeYukle,
  type KurulumDurumu,
} from '../../api/kurulum';
import { KurulumSayfasi } from './KurulumSayfasi';

vi.mock('../../api/kurulum');
const durumGetir = vi.mocked(kurulumDurumu);
const markaYaz = vi.mocked(markaKaydet);
const onizle = vi.mocked(subeOnizle);
const yukle = vi.mocked(subeYukle);

const DURUM: KurulumDurumu = {
  steps: [
    { step: 'brand', label: 'Marka', done: false, detail: 'Marka adı bekleniyor' },
    { step: 'branches', label: 'Şubeler', done: false, detail: 'Henüz şube yok' },
    { step: 'template', label: 'Şablon', done: false, detail: 'Kütüphaneden seçin' },
    { step: 'plan', label: 'Plan', done: false, detail: 'Henüz plan yok' },
    { step: 'staff', label: 'Personel', done: false, detail: 'Davet gönderilmedi' },
    { step: 'review', label: 'Özet ve yayın', done: false, detail: 'Gözden geçirin' },
  ],
  current: 'brand',
  order: ['brand', 'branches', 'template', 'plan', 'staff', 'review'],
  publishable: false,
  completed_at: null,
  brand: null,
};

function kur() {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={istemci}>
      <KurulumSayfasi />
    </QueryClientProvider>,
  );
}

describe('KurulumSayfasi', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    durumGetir.mockResolvedValue(DURUM);
  });

  it('kaldığı adımı açar', async () => {
    // TC-004: durum sunucudan okunuyor, panelde sayaç yok.
    durumGetir.mockResolvedValue({
      ...DURUM,
      current: 'branches',
      steps: DURUM.steps.map((a) => (a.step === 'brand' ? { ...a, done: true } : a)),
    });

    kur();

    expect(await screen.findByText('Adım 2 · Şubeler')).toBeInTheDocument();
  });

  it('marka kaydedilince durum tazelenir', async () => {
    markaYaz.mockResolvedValue({ ...DURUM, current: 'branches' });
    kur();

    await userEvent.type(await screen.findByLabelText('Marka adı'), 'Kahve Durağı');
    await userEvent.click(screen.getByRole('button', { name: 'Kaydet ve devam et' }));

    expect(markaYaz).toHaveBeenCalledWith(
      expect.objectContaining({ brand_name: 'Kahve Durağı', timezone: 'Europe/Istanbul' }),
    );
  });

  it('marka adı boşken kaydetme kapalı', async () => {
    kur();

    await screen.findByLabelText('Marka adı');

    expect(screen.getByRole('button', { name: 'Kaydet ve devam et' })).toBeDisabled();
  });

  it('dosya seçilince önizleme gösterilir, yazma ayrı adım', async () => {
    durumGetir.mockResolvedValue({ ...DURUM, current: 'branches' });
    onizle.mockResolvedValue({
      total: 10,
      accepted: 9,
      error_rows: 1,
      created: 0,
      updated: 0,
      rejected: false,
      errors: [{ row: 7, field: 'kod', message: 'Şube kodu zorunlu' }],
      branches: [],
    });
    kur();

    const alan = await screen.findByLabelText('Doldurduğunuz dosya');
    await userEvent.upload(
      alan,
      new File(['x'], 'subeler.xlsx', { type: 'application/vnd.ms-excel' }),
    );

    expect(await screen.findByText('9 satır hazır')).toBeInTheDocument();
    expect(screen.getByText('1 satır hatalı')).toBeInTheDocument();
    expect(screen.getByText('Şube kodu zorunlu')).toBeInTheDocument();
    // Önizleme yazmaz: yükleme düğmesi hâlâ bekliyor.
    expect(screen.getByRole('button', { name: '9 şubeyi yükle' })).toBeEnabled();
    expect(yukle).not.toHaveBeenCalled();
  });

  it('reddedilen dosyada hata raporu düğmesi çıkar', async () => {
    durumGetir.mockResolvedValue({ ...DURUM, current: 'branches' });
    onizle.mockRejectedValue({
      type: 'urn:talimatname:yukleme-reddedildi',
      title: 'Dosya kabul edilmedi',
      status: 422,
    });
    kur();

    const alan = await screen.findByLabelText('Doldurduğunuz dosya');
    await userEvent.upload(
      alan,
      new File(['x'], 'subeler.xlsx', { type: 'application/vnd.ms-excel' }),
    );

    expect(await screen.findByRole('alert')).toHaveTextContent('Dosya kabul edilmedi');
    expect(screen.getByRole('button', { name: 'Hatalı satırları indir' })).toBeInTheDocument();
  });

  it('yayın için eksik varsa düğme kapalı ve sebebi yazılı', async () => {
    durumGetir.mockResolvedValue({ ...DURUM, current: 'review' });
    kur();

    expect(await screen.findByRole('alert')).toHaveTextContent('en az bir şube');
    expect(screen.getByRole('button', { name: 'Yayınla' })).toBeDisabled();
  });
});
