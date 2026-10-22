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
    });

    kur();

    expect(await screen.findByText('API çalışıyor')).toBeInTheDocument();
    expect(screen.getByText('0.1.0')).toBeInTheDocument();
    expect(screen.getAllByText('yapılandırılmamış')).toHaveLength(2);
  });

  it('API ulaşılamazsa uyarı ve yeniden deneme düğmesi gösterilir', async () => {
    getir.mockRejectedValue(new Error('ağ yok'));

    kur();

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('API ulaşılamıyor')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Yeniden dene' })).toBeInTheDocument();
  });
});
