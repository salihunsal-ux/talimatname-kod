/** Aksiyon veri erişimi (ST-069). */
import { api } from './client';
import type { components } from './schema';

export type AksiyonOzet = components['schemas']['AksiyonOzet'];
export type ElleAksiyonGirdisi = components['schemas']['ElleAksiyonGirdisi'];
export type AksiyonSayaclari = components['schemas']['AksiyonSayaclari'];
export type Oncelik = ElleAksiyonGirdisi['priority'];

export async function aksiyonListesi(secenek: {
  durum?: 'open' | 'closed' | 'all';
  branchId?: string;
  yalnizGecikmis?: boolean;
}): Promise<AksiyonOzet[]> {
  const { data, error } = await api.GET('/api/v1/actions', {
    params: {
      query: {
        action_status: secenek.durum ?? 'open',
        branch_id: secenek.branchId,
        only_overdue: secenek.yalnizGecikmis ?? false,
      },
    },
  });
  if (error) throw error;
  return data;
}

export async function aksiyonSayaclari(): Promise<AksiyonSayaclari> {
  const { data, error } = await api.GET('/api/v1/actions/counts');
  if (error) throw error;
  return data;
}

export async function aksiyonAc(girdi: ElleAksiyonGirdisi): Promise<AksiyonOzet> {
  const { data, error } = await api.POST('/api/v1/actions', { body: girdi });
  if (error) throw error;
  return data;
}

export async function aksiyonKapat(id: string, note: string): Promise<AksiyonOzet> {
  const { data, error } = await api.POST('/api/v1/actions/{action_id}/close', {
    params: { path: { action_id: id } },
    body: { note, closed_by: null },
  });
  if (error) throw error;
  return data;
}
