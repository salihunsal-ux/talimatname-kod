/** Pano veri erişimi (ST-078). */
import { api } from './client';
import type { components } from './schema';

export type PanoYaniti = components['schemas']['PanoYaniti'];
export type Satir = components['schemas']['Satir'];
export type Hucre = components['schemas']['Hucre'];

export async function panoGetir(gun?: string): Promise<PanoYaniti> {
  const { data, error } = await api.GET('/api/v1/dashboard', {
    params: { query: { business_day: gun } },
  });
  if (error) throw error;
  return data;
}
