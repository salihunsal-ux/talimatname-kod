/** Çalıştırma görünümü (ST-048/079 panel tarafı). */
import { api } from './client';
import type { components } from './schema';

export type CalistirmaGorunumu = components['schemas']['CalistirmaGorunumu'];
export type MaddeDurumu = components['schemas']['MaddeDurumu'];

export async function calistirmaGorunumu(id: string): Promise<CalistirmaGorunumu> {
  const { data, error } = await api.GET('/api/v1/runs/{run_id}', {
    params: { path: { run_id: id } },
  });
  if (error) throw error;
  return data;
}
