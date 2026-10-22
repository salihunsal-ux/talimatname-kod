/**
 * Sistem uç noktalarının veri erişim katmanı.
 *
 * Bileşenler taşımadan (openapi-fetch) habersizdir: böylece birim testi
 * global `fetch`'i taklit etmek zorunda kalmaz ve uç nokta değişince tek
 * dosya değişir. Gerçek kablolama Playwright duman testiyle doğrulanır.
 */
import { api } from './client';
import type { components } from './schema';

export type SistemDurumu = components['schemas']['HealthResponse'];

export async function sistemDurumuGetir(): Promise<SistemDurumu> {
  const { data, error } = await api.GET('/api/v1/health');
  if (error) throw error;
  return data;
}
