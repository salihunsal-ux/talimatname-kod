import { api } from './client';
import type { components } from './schema';

export type Kanit = components['schemas']['KanitOzet'];

/** Hangi kopya: ızgarada küçük resim, tam boyda damgalı kopya (FR-0606). */
export type KanitKopyasi = 'raw' | 'stamped' | 'thumbnail';

export async function calistirmaKanitlari(runId: string): Promise<Kanit[]> {
  const { data, error } = await api.GET('/api/v1/runs/{run_id}/evidence', {
    params: { path: { run_id: runId } },
  });
  if (error) throw error;
  return data;
}

/**
 * 15 dakikalık imzalı bağlantı (FR-1305). Her görüntülemede yeniden
 * alınır: bağlantıyı saklamak, süresini uzatmaya çalışmak demek olurdu.
 */
export async function kanitBaglantisi(
  evidenceId: string,
  variant: KanitKopyasi = 'thumbnail',
): Promise<string> {
  const { data, error } = await api.GET('/api/v1/evidence/{evidence_id}/url', {
    params: { path: { evidence_id: evidenceId }, query: { variant } },
  });
  if (error) throw error;
  return data.url;
}
