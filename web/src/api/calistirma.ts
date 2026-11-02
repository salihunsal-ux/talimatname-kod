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

/**
 * Çalıştırma PDF'i (FR-1213): denetçiye verilen kâğıt.
 *
 * Belirteç ara katmandan geliyor; `<a href>` ile indirmek belirteci
 * URL'ye koymak demek olurdu.
 */
export async function calistirmaPdf(runId: string): Promise<Blob> {
  const { data, error } = await api.GET('/api/v1/runs/{run_id}/pdf', {
    params: { path: { run_id: runId } },
    parseAs: 'blob',
  });
  if (error) throw error;
  return data;
}

/** Yapılmayacak (FR-0514). Sebep zorunlu; sunucu da boş kabul etmiyor. */
export async function calistirmaIptal(id: string, sebep: string): Promise<CalistirmaGorunumu> {
  const { data, error } = await api.POST('/api/v1/runs/{run_id}/cancel', {
    params: { path: { run_id: id } },
    body: { reason: sebep },
  });
  if (error) throw error;
  return data;
}
