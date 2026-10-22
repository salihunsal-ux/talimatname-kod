/**
 * Şube veri erişimi. Bileşenler taşımadan habersiz (ADR-0014 md.2);
 * birim testleri bu modülü taklit eder, uçtan uca doğrulama Playwright'ta.
 */
import { api } from './client';
import type { components } from './schema';

export type BolgeDugumu = components['schemas']['BolgeDugumu'];
export type SubeOzet = components['schemas']['SubeOzet'];
export type SubeDetay = components['schemas']['SubeDetay'];
export type SubeGirdisi = components['schemas']['SubeGirdisi'];

export async function subeAgaci(dahilPasif = false): Promise<BolgeDugumu[]> {
  const { data, error } = await api.GET('/api/v1/branches', {
    params: { query: { include_inactive: dahilPasif } },
  });
  if (error) throw error;
  return data;
}

export async function subeDetayi(id: string): Promise<SubeDetay> {
  const { data, error } = await api.GET('/api/v1/branches/{branch_id}', {
    params: { path: { branch_id: id } },
  });
  if (error) throw error;
  return data;
}

export async function subeEkle(girdi: SubeGirdisi): Promise<SubeOzet> {
  const { data, error } = await api.POST('/api/v1/branches', { body: girdi });
  if (error) throw error;
  return data;
}

export async function subePasiflestir(id: string): Promise<SubeOzet> {
  const { data, error } = await api.POST('/api/v1/branches/{branch_id}/deactivate', {
    params: { path: { branch_id: id } },
  });
  if (error) throw error;
  return data;
}
