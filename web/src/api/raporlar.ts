/**
 * Rapor veri erişimi (ST-090; FR-1207, FR-1208, FR-1220).
 *
 * Kapsam süzgeci sunucuda: bölge müdürü bölgesini, şube müdürü
 * şubesini görüyor. Panel kapsam hesaplamıyor.
 */
import { api } from './client';
import type { components } from './schema';

export type AylikOzet = components['schemas']['AylikOzet'];
export type SubeOzeti = components['schemas']['SubeOzeti'];
export type OlcumSerisi = components['schemas']['OlcumSerisi'];
export type GaleriKanidi = components['schemas']['GaleriKanidi'];

export async function aylikOzet(yil: number, ay: number): Promise<AylikOzet> {
  const { data, error } = await api.GET('/api/v1/reports/monthly', {
    params: { query: { year: yil, month: ay } },
  });
  if (error) throw error;
  return data;
}

export async function olcumGunlugu(
  ilkGun: string,
  sonGun: string,
  yalnizAralikDisi = false,
): Promise<OlcumSerisi[]> {
  const { data, error } = await api.GET('/api/v1/reports/measurements', {
    params: {
      query: { first_day: ilkGun, last_day: sonGun, only_out_of_range: yalnizAralikDisi },
    },
  });
  if (error) throw error;
  return data;
}

export async function kanitGalerisi(
  ilkGun: string,
  sonGun: string,
  yalnizBayrakli = false,
): Promise<GaleriKanidi[]> {
  const { data, error } = await api.GET('/api/v1/reports/gallery', {
    params: { query: { first_day: ilkGun, last_day: sonGun, only_flagged: yalnizBayrakli } },
  });
  if (error) throw error;
  return data;
}
