import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  kurulumDurumu,
  kurulumYayinla,
  kutuphane,
  markaKaydet,
  personelOnizle,
  planOlustur,
  planOnerisi,
  sablonKopyala,
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
const kutuphaneGetir = vi.mocked(kutuphane);
const sablonSec = vi.mocked(sablonKopyala);
const oneriGetir = vi.mocked(planOnerisi);
const planYaz = vi.mocked(planOlustur);
const yayinla = vi.mocked(kurulumYayinla);
const personelOnizleme = vi.mocked(personelOnizle);

const KUTUPHANE = [
  {
    key: 'kapanis-kafe',
    name: 'Kapanış (kafe / hızlı servis)',
    category: 'Kapanış',
    summary: 'Gün sonunda hijyen ve güvenli kapanış.',
    item_count: 15,
    critical_count: 4,
    photo_count: 4,
    window: 'Günlük · şube kapanış saatinden 60 dk önce başlar',
  },
];

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

  it('kütüphane şablonları ölçüleriyle listelenir', async () => {
    durumGetir.mockResolvedValue({ ...DURUM, current: 'template' });
    kutuphaneGetir.mockResolvedValue(KUTUPHANE);
    kur();

    expect(await screen.findByText('Kapanış (kafe / hızlı servis)')).toBeInTheDocument();
    expect(screen.getByText('15 madde')).toBeInTheDocument();
    expect(screen.getByText('4 kritik')).toBeInTheDocument();
    expect(screen.getByText(/kapanış saatinden 60 dk önce/)).toBeInTheDocument();
  });

  it('şablon seçimi hesaba kopyalar', async () => {
    durumGetir.mockResolvedValue({ ...DURUM, current: 'template' });
    kutuphaneGetir.mockResolvedValue(KUTUPHANE);
    sablonSec.mockResolvedValue({ version_id: 's-1' });
    kur();

    await userEvent.click(await screen.findByRole('button', { name: 'Bu şablonu kullan' }));

    expect(sablonSec).toHaveBeenCalledWith('kapanis-kafe');
  });

  it('plan önerisi şube saatinden türetilir ve kaydedilebilir', async () => {
    durumGetir.mockResolvedValue({ ...DURUM, current: 'plan' });
    oneriGetir.mockResolvedValue({
      name: 'Kapanış · Kahve Durağı',
      template_version_id: 's-1',
      branch_ids: ['b-1', 'b-2'],
      recurrence: 'FREQ=DAILY',
      anchor_reference: 'close',
      anchor_offset_minutes: -60,
      duration_minutes: 150,
      tolerance_minutes: 120,
      window: 'Günlük · şube kapanış saatinden 60 dk önce başlar',
    });
    planYaz.mockResolvedValue(DURUM);
    kur();

    expect(await screen.findByText('2 şube')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Planı oluştur' }));

    expect(planYaz).toHaveBeenCalledWith('Kapanış · Kahve Durağı');
  });

  it('yayın sonucu hazır çalıştırma sayısını söyler', async () => {
    durumGetir.mockResolvedValue({ ...DURUM, current: 'review', publishable: true });
    yayinla.mockResolvedValue({
      runs_ready: 75,
      first_window: '2026-10-24T04:15:00Z',
      status: DURUM,
    });
    kur();

    await userEvent.click(await screen.findByRole('button', { name: 'Yayınla' }));

    expect(await screen.findByText(/75 çalıştırma hazır/)).toBeInTheDocument();
  });

  it('personel adımı aynı yükleme akışını kullanır', async () => {
    durumGetir.mockResolvedValue({ ...DURUM, current: 'staff' });
    personelOnizleme.mockResolvedValue({
      total: 3,
      accepted: 3,
      error_rows: 0,
      created: 0,
      updated: 0,
      rejected: false,
      errors: [],
      branches: [],
    });
    kur();

    const alan = await screen.findByLabelText('Doldurduğunuz dosya');
    await userEvent.upload(
      alan,
      new File(['x'], 'personel.xlsx', { type: 'application/vnd.ms-excel' }),
    );

    expect(await screen.findByText('3 satır hazır')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '3 kişiyi davet et' })).toBeEnabled();
    // Şube yükleyicisi çağrılmadı: adımlar birbirine karışmıyor.
    expect(onizle).not.toHaveBeenCalled();
  });

  it('yayın için eksik varsa düğme kapalı ve sebebi yazılı', async () => {
    durumGetir.mockResolvedValue({ ...DURUM, current: 'review' });
    kur();

    expect(await screen.findByRole('alert')).toHaveTextContent('en az bir şube');
    expect(screen.getByRole('button', { name: 'Yayınla' })).toBeDisabled();
  });
});
