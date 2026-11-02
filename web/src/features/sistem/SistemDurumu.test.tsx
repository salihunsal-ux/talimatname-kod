import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { sistemDurumuGetir } from '../../api/sistem';
import { SistemDurumu } from './SistemDurumu';

vi.mock('../../api/sistem');
const getir = vi.mocked(sistemDurumuGetir);

function kur() {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={istemci}>
      <SistemDurumu />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getir.mockReset();
});

describe('SistemDurumu', () => {
  it('API yanıt verince sürüm ve ortam gösterilir', async () => {
    getir.mockResolvedValue({
      status: 'ok',
      version: '0.1.0',
      environment: 'dev',
      database_configured: false,
      object_store_configured: false,
      demo_show_otp_code: false,
      timestamping_configured: false,
    });

    kur();

    expect(await screen.findByText('API çalışıyor')).toBeInTheDocument();
    expect(screen.getByText('0.1.0')).toBeInTheDocument();
    expect(screen.getAllByText('yapılandırılmamış')).toHaveLength(2);
  });

  it('çıpalama kapalıyken bunun ne anlama geldiğini yazar', async () => {
    getir.mockResolvedValue({
      status: 'ok',
      version: '0.1.0',
      environment: 'prod',
      database_configured: true,
      object_store_configured: true,
      demo_show_otp_code: false,
      timestamping_configured: false,
    });

    kur();

    // Kapalıyken sessizce "güvenli" demiyoruz (FR-1302).
    expect(await screen.findByText(/tek tek değişiklikleri gösterir/)).toBeInTheDocument();
  });

  it('çıpalama açıkken açık yazar', async () => {
    getir.mockResolvedValue({
      status: 'ok',
      version: '0.1.0',
      environment: 'prod',
      database_configured: true,
      object_store_configured: true,
      demo_show_otp_code: false,
      timestamping_configured: true,
    });

    kur();

    expect(await screen.findByText('açık')).toBeInTheDocument();
  });

  it('demo modu açıkken tek faktöre indiğini yazar', async () => {
    getir.mockResolvedValue({
      status: 'ok',
      version: '0.1.0',
      environment: 'staging',
      database_configured: true,
      object_store_configured: true,
      demo_show_otp_code: true,
      timestamping_configured: false,
    });

    kur();

    // Açık kapıyı kapalı sanmak, kapalı kapıdan tehlikeli.
    expect(await screen.findByText(/tek faktöre iniyor/)).toBeInTheDocument();
  });

  it('API ulaşılamazsa uyarı ve yeniden deneme düğmesi gösterilir', async () => {
    getir.mockRejectedValue(new Error('ağ yok'));

    kur();

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('API ulaşılamıyor')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Yeniden dene' })).toBeInTheDocument();
  });
});
