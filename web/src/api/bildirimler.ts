import { api } from './client';
import type { components } from './schema';

export type Bildirim = components['schemas']['BildirimOzet'];
export type BildirimSayaclari = components['schemas']['BildirimSayaclari'];

export type BildirimDurumu = NonNullable<Bildirim['status']> | 'all';

export async function bildirimListesi(status: BildirimDurumu = 'all'): Promise<Bildirim[]> {
  const { data, error } = await api.GET('/api/v1/notifications', {
    params: { query: { delivery_status: status } },
  });
  if (error) throw error;
  return data;
}

export async function bildirimSayaclari(): Promise<BildirimSayaclari> {
  const { data, error } = await api.GET('/api/v1/notifications/counts');
  if (error) throw error;
  return data;
}
