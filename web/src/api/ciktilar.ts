/**
 * Arka plan çıktıları (FR-1217).
 *
 * Dönem PDF uç noktaları iki şey dönebiliyor: küçük rapor **dosya**,
 * eşiği geçen rapor bir **iş kaydı** (202). Kararı sunucu veriyor;
 * panelin işi ikisini de karşılamak.
 */
import { api } from './client';
import type { components } from './schema';

export type CiktiIsi = components['schemas']['CiktiIsi'];

/** PDF isteğinin sonucu: ya dosya geldi ya da iş kuyruğa girdi. */
export type PdfSonucu = { tur: 'dosya'; blob: Blob } | { tur: 'is'; is: CiktiIsi };

/**
 * 202 gövdesi de blob olarak çözülüyor (istek `parseAs: 'blob'`
 * diyor); metne çevirip okuyoruz. Durum koduna bakmak şart: iki
 * yanıtın da gövdesi var ve ayrımı yalnızca kod söylüyor.
 */
export async function pdfSonucu(veri: Blob, durum: number): Promise<PdfSonucu> {
  if (durum === 202) return { tur: 'is', is: JSON.parse(await veri.text()) as CiktiIsi };
  return { tur: 'dosya', blob: veri };
}

export async function ciktilarim(): Promise<CiktiIsi[]> {
  const { data, error } = await api.GET('/api/v1/reports/exports');
  if (error) throw error;
  return data;
}

export async function ciktiDosyasi(isId: string): Promise<Blob> {
  const { data, error } = await api.GET('/api/v1/reports/exports/{job_id}/dosya', {
    params: { path: { job_id: isId } },
    parseAs: 'blob',
  });
  if (error) throw error;
  return data;
}

/** Hâlâ üretilen bir iş var mı: liste ona göre tazeleniyor. */
export function bekleyenVar(isler: CiktiIsi[]): boolean {
  return isler.some((i) => i.state === 'queued' || i.state === 'running');
}
