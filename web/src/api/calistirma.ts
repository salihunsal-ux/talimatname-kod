/** Çalıştırma görünümü (ST-048/079 panel tarafı). */
import { api } from './client';
import type { components } from './schema';

export type CalistirmaGorunumu = components['schemas']['CalistirmaGorunumu'];
export type MaddeDurumu = components['schemas']['MaddeDurumu'];
export type CevapCiktisi = components['schemas']['CevapCiktisi'];

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

/**
 * Listeyi üstlen: kilidi açıkça al (BR-26).
 *
 * Yazmak kilidi zaten alıyordu; bu çağrı niyeti öne çekiyor, böylece
 * ikinci kişi ilk maddenin yazılmasını beklemeden "X yapıyor" görüyor.
 */
export async function listeyiUstlen(id: string): Promise<CalistirmaGorunumu> {
  const { data, error } = await api.POST('/api/v1/runs/{run_id}/claim', {
    params: { path: { run_id: id } },
  });
  if (error) throw error;
  return data;
}

/** Kilidi bırak; müdür çağırırsa başkasınınki de kalkar (BR-26). */
export async function kilidiBirak(id: string): Promise<CalistirmaGorunumu> {
  const { data, error } = await api.POST('/api/v1/runs/{run_id}/release', {
    params: { path: { run_id: id } },
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
