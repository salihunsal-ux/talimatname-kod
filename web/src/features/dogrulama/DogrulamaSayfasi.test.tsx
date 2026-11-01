import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { belgeDogrula, type DogrulamaSonucu } from '../../api/dogrulama';
import { DogrulamaSayfasi } from './DogrulamaSayfasi';

vi.mock('../../api/dogrulama');
const sor = vi.mocked(belgeDogrula);

const KAYIT: DogrulamaSonucu = {
  code: 'A1B2-C3D4-E5F6',
  document: 'calistirma',
  document_label: 'Çalıştırma raporu',
  issued_at: '2026-11-01T06:30:00Z',
  timezone: 'Europe/Istanbul',
  period: '2026-11-01',
  branch_code: 'KDK',
  record_intact: true,
  chain_linked: true,
};

function kur(kod = '') {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={istemci}>
      <DogrulamaSayfasi kod={kod} />
    </QueryClientProvider>,
  );
}

describe('DogrulamaSayfasi', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('bağlantıdaki kod kendiliğinden sorulur', async () => {
    sor.mockResolvedValue(KAYIT);

    kur('A1B2-C3D4-E5F6');

    expect(await screen.findByText(/kaydı değişmemiş/)).toBeInTheDocument();
    expect(sor).toHaveBeenCalledWith('A1B2-C3D4-E5F6');
  });

  it('kâğıtla karşılaştırılacak alanları gösterir, fazlasını değil', async () => {
    sor.mockResolvedValue(KAYIT);

    kur('A1B2-C3D4-E5F6');

    const liste = (await screen.findByText('Şube')).closest('dl');
    expect(liste).toHaveTextContent('KDK');
    expect(liste).toHaveTextContent('Çalıştırma raporu');
    expect(liste).toHaveTextContent('2026-11-01');
    // Kâğıtta yazmayan hiçbir şey: puan, kişi, IP (BR-21).
    expect(liste?.textContent).not.toMatch(/%|puan|IP/i);
  });

  it('üretim saatini hesabın saat diliminde gösterir', async () => {
    sor.mockResolvedValue(KAYIT);

    kur('A1B2-C3D4-E5F6');

    // 06:30 UTC, İstanbul'da 09:30: kâğıtta yazan saat de bu.
    expect(await screen.findByText(/09:30/)).toBeInTheDocument();
  });

  it('kayda dokunulmuşsa "sağlam" demez', async () => {
    sor.mockResolvedValue({ ...KAYIT, record_intact: false });

    kur('A1B2-C3D4-E5F6');

    expect(await screen.findByRole('status')).toHaveTextContent('doğrulaması tutmuyor');
    expect(screen.queryByText(/kaydı değişmemiş/)).not.toBeInTheDocument();
  });

  it('kod yoksa sorgu yapılmaz, elle yazılabilir', async () => {
    sor.mockResolvedValue(KAYIT);
    kur();

    expect(sor).not.toHaveBeenCalled();

    const kullanici = userEvent.setup();
    await kullanici.type(screen.getByLabelText('Belge kodu'), 'a1b2c3d4e5f6');
    await kullanici.click(screen.getByRole('button', { name: 'Doğrula' }));

    expect(sor).toHaveBeenCalledWith('a1b2c3d4e5f6');
    expect(await screen.findByRole('status')).toBeInTheDocument();
  });

  it('bulunamayan kod için ne yapılacağını söyler', async () => {
    sor.mockRejectedValue({
      type: 'urn:talimatname:belge-bulunamadi',
      title: 'Bu koda ait belge kaydı yok',
      status: 404,
    });

    kur('A1B2-C3D4-E5F6');

    expect(await screen.findByRole('alert')).toHaveTextContent('Kodu kâğıttan yeniden okuyun');
  });

  it('hız sınırı aşıldığında bekleme süresini söyler', async () => {
    sor.mockRejectedValue({
      type: 'urn:talimatname:cok-fazla-deneme',
      title: 'Çok fazla deneme',
      status: 429,
    });

    kur('A1B2-C3D4-E5F6');

    expect(await screen.findByRole('alert')).toHaveTextContent('Bir dakika sonra');
  });

  it('neyi doğrulamadığını da yazar', async () => {
    sor.mockResolvedValue(KAYIT);

    kur('A1B2-C3D4-E5F6');

    expect(await screen.findByText(/raporun içeriğini göstermez/)).toBeInTheDocument();
  });
});
