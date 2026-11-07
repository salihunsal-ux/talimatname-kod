import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { bildirimListesi, bildirimSayaclari } from '../../api/bildirimler';
import { Oturumlu } from '../../test/oturum';
import { BildirimlerSayfasi } from './BildirimlerSayfasi';

vi.mock('../../api/bildirimler');
const liste = vi.mocked(bildirimListesi);
const sayac = vi.mocked(bildirimSayaclari);

const GONDERILEMEYEN = {
  id: 'b-1',
  kind: 'run_opened',
  kind_label: 'Liste açıldı',
  channel: 'push' as const,
  user_id: 'k-1',
  user_name: 'Emre Personel',
  title: 'Günlük kapanış başladı',
  body: 'Kadıköy · liste şimdi açıldı',
  send_at: '2026-10-23T19:00:00Z',
  status: 'failed' as const,
  status_label: 'Gönderilemedi',
  attempts: 1,
  error_code: 'surucu-yok',
  error_detail: 'push sürücüsü bağlı değil',
};

function kur() {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={istemci}>
      <Oturumlu>
        <BildirimlerSayfasi />
      </Oturumlu>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  liste.mockResolvedValue([GONDERILEMEYEN]);
  sayac.mockResolvedValue({
    queued: 2,
    sent: 0,
    failed: 1,
    total: 3,
    drivers_connected: [],
  });
});

describe('Bildirimler sayfası', () => {
  it('seçili süzgeç aria-pressed ile işaretli', async () => {
    // Seçili görünüm bu öznitelikten türüyor (bilesenler.css).
    kur();

    const hepsi = await screen.findByRole('button', { name: 'Hepsi' });
    expect(hepsi).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Kuyrukta' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('kanal bağlı değilken bunu açıkça söyler', async () => {
    kur();

    const uyari = await screen.findByRole('status');
    expect(uyari).toHaveTextContent('Hiçbir bildirim kanalı bağlı değil');
    expect(uyari).toHaveTextContent('kimseye ulaşmıyor');
  });

  it('başarısız gönderimin sebebini Türkçe yazar, ham kodu değil', async () => {
    // Eskiden satırda "surucu-yok" yazıyordu ve bu test onu doğruluyordu.
    // Makine kodu kullanıcı metni değil (bağımsız test turu D-1): sunucu
    // zaten Türkçe `error_detail` gönderiyor, kod `title`da duruyor.
    kur();

    expect(await screen.findByText('Günlük kapanış başladı')).toBeInTheDocument();
    // 'Gönderilemedi' hem süzgeç düğmesinde hem satırda geçiyor: satırdakine bakıyoruz.
    const satir = within(screen.getByRole('table'));
    expect(satir.getByText('Gönderilemedi')).toBeInTheDocument();
    expect(satir.getByText('push sürücüsü bağlı değil')).toBeInTheDocument();
    expect(satir.queryByText('surucu-yok')).not.toBeInTheDocument();
    expect(satir.getByTitle('surucu-yok')).toBeInTheDocument();
  });

  it('sunucu açıklama göndermezse kodun Türkçe karşılığını yazar', async () => {
    // Yedek yol: eski kayıtlarda `error_detail` boş olabiliyor.
    liste.mockResolvedValue([
      { ...GONDERILEMEYEN, error_code: 'alici-pasif', error_detail: null },
    ] as never);
    kur();

    const satir = within(await screen.findByRole('table'));
    expect(satir.getByText('Alıcı pasif: bildirim gönderilmedi')).toBeInTheDocument();
    expect(satir.queryByText('alici-pasif')).not.toBeInTheDocument();
  });

  it('kanal bağlandığında uyarı yerine kanal adı yazar', async () => {
    sayac.mockResolvedValue({
      queued: 0,
      sent: 5,
      failed: 0,
      total: 5,
      drivers_connected: ['push'],
    });

    kur();

    const durum = await screen.findByRole('status');
    expect(durum).toHaveTextContent('Bağlı kanallar: push');
    expect(durum).not.toHaveTextContent('bağlı değil');
  });
});
