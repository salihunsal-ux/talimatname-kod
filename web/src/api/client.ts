/**
 * API istemcisi. Tipler OpenAPI'den **üretilir** (ADR-0014 md.10):
 *   npm run api:tipler
 * Elle tip yazılmaz; sözleşme kayması derleme hatasıdır.
 */
import createClient from 'openapi-fetch';

import type { paths } from './schema';

// Varsayılan: **aynı kaynak**. Geliştirmede Vite `/api` isteklerini
// backend'e aktarır (vite.config.ts), üretimde panel API ile aynı alan
// adından servis edilir. Ayrı bir adres gerekiyorsa VITE_API_URL verilir.
const taban = import.meta.env.VITE_API_URL ?? '';

export const api = createClient<paths>({ baseUrl: taban });

/** RFC 9457 problem+json gövdesi (ADR-0014 md.8). */
export type Problem = {
  type: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
  errors?: { alan: string; sebep: string }[];
};

/**
 * Hata nesnesinden problem gövdesini çıkarır. İstemci davranışı `type`
 * alanına bakar — Türkçe `title` metni değişebilir, `type` sözleşmedir.
 */
export function problemCoz(hata: unknown): Problem | null {
  if (typeof hata !== 'object' || hata === null) return null;
  // openapi-fetch hatayı doğrudan gövde olarak fırlatır; bazı sarmalayıcılar
  // `{ error: gövde }` biçiminde verir — ikisini de kabul ediyoruz.
  const aday = 'error' in hata ? (hata as { error: unknown }).error : hata;
  if (typeof aday === 'object' && aday !== null && 'type' in aday && 'title' in aday) {
    return aday as Problem;
  }
  return null;
}
