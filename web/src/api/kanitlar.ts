import { api } from './client';
import type { components } from './schema';

export type Kanit = components['schemas']['KanitOzet'];

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
export async function kanitBaglantisi(evidenceId: string): Promise<string> {
  const { data, error } = await api.GET('/api/v1/evidence/{evidence_id}/url', {
    params: { path: { evidence_id: evidenceId } },
  });
  if (error) throw error;
  return data.url;
}
