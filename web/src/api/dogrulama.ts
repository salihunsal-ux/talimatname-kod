/**
 * Belge doğrulama (FR-1218). **Oturumsuz** uç nokta: kâğıdı eline alan
 * denetçi panele giremez.
 */
import { api } from './client';
import type { components } from './schema';

export type DogrulamaSonucu = components['schemas']['DogrulamaYaniti'];

export async function belgeDogrula(kod: string): Promise<DogrulamaSonucu> {
  const { data, error } = await api.GET('/api/v1/verify/{code}', {
    params: { path: { code: kod } },
  });
  if (error) throw error;
  return data;
}
