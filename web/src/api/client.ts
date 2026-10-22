/**
 * API istemcisi. Tipler OpenAPI'den **üretilir** (ADR-0014 md.10):
 *   npm run api:tipler
 * Elle tip yazılmaz; sözleşme kayması derleme hatasıdır.
 */
import createClient from 'openapi-fetch';

import type { paths } from './schema';

// Varsayılan 8010: bu makinede 8000 başka bir projeye ait (bkz. README).
// Ortama göre VITE_API_URL ile ezilir.
const taban = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8010';

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
  if (typeof hata === 'object' && hata !== null && 'type' in hata && 'title' in hata) {
    return hata as Problem;
  }
  return null;
}
