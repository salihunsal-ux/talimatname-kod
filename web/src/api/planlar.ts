/** Plan ve çalıştırma veri erişimi (ST-029). */
import { api } from './client';
import type { components } from './schema';

export type PlanOzet = components['schemas']['PlanOzet'];
export type PlanGirdisi = components['schemas']['PlanGirdisi'];
export type Zamanlama = components['schemas']['Zamanlama'];
export type CalistirmaOzet = components['schemas']['CalistirmaOzet'];
export type OnizlemeYaniti = components['schemas']['OnizlemeYaniti'];

export async function planListesi(includeInactive = false): Promise<PlanOzet[]> {
  const { data, error } = await api.GET('/api/v1/plans', {
    params: { query: { include_inactive: includeInactive } },
  });
  if (error) throw error;
  return data;
}

export async function planOnizleme(girdi: PlanGirdisi): Promise<OnizlemeYaniti> {
  const { data, error } = await api.POST('/api/v1/plans/preview', { body: girdi });
  if (error) throw error;
  return data;
}

export async function planOlustur(girdi: PlanGirdisi): Promise<PlanOzet> {
  const { data, error } = await api.POST('/api/v1/plans', { body: girdi });
  if (error) throw error;
  return data;
}

export async function planDurdur(id: string): Promise<PlanOzet> {
  const { data, error } = await api.POST('/api/v1/plans/{plan_id}/deactivate', {
    params: { path: { plan_id: id } },
  });
  if (error) throw error;
  return data;
}

export async function gununCalistirmalari(gun?: string): Promise<CalistirmaOzet[]> {
  const { data, error } = await api.GET('/api/v1/runs', {
    params: { query: { business_day: gun } },
  });
  if (error) throw error;
  return data;
}
