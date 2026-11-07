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
 * Sunucunun problem+json **olmayan** hata yanıtı (ara sunucunun HTML
 * 500'ü, ağ geçidinin düz metni) istemci tarafında üretilen problem
 * gövdesine çevrilir.
 *
 * Neden: openapi-fetch gövdeyi çözemediğinde hem `data` hem `error`
 * boş dönüyor; çağrı yeri `if (error) throw` ile kurtulamıyor ve
 * ekran tanımsız veriyle çiziliyordu. Giriş ekranı böyle beyaz
 * kalıyordu (API kapalıyken tarayıcıda görüldü) — yani sunucu
 * düştüğünde kullanıcı hata yerine boş sayfa görüyordu.
 */
api.use({
  onResponse({ response }) {
    if (response.ok) return response;
    if ((response.headers.get('content-type') ?? '').includes('json')) return response;
    const problem: Problem = {
      type: 'urn:talimatname:yanit-cozulemedi',
      title: 'Sunucuya ulaşılamadı',
      status: response.status,
      detail: `Sunucu beklenmeyen bir yanıt verdi (HTTP ${response.status}).`,
    };
    throw problem;
  },
});

/**
 * Hata nesnesinden problem gövdesini çıkarır. İstemci davranışı `type`
 * alanına bakar — Türkçe `title` metni değişebilir, `type` sözleşmedir.
 */
/**
 * Sunucunun alan hatalarını `{alan: sebep}` sözlüğüne çevirir.
 *
 * Form bunu alanın yanına yazıyor ve alanı `aria-invalid` yapıyor:
 * ortak kutuda duran cümle hangi alana ait olduğunu söylemiyordu
 * (bağımsız test turu D-4).
 */
export function alanHatalari(hata: unknown): Record<string, string> {
  const problem = problemCoz(hata);
  const cikti: Record<string, string> = {};
  for (const alan of problem?.errors ?? []) {
    // Aynı alandan birden çok sebep gelirse ilki yazılır: kullanıcıya
    // tek cümle yeter, listenin tamamı ortak kutuda zaten var.
    if (alan.alan && !(alan.alan in cikti)) cikti[alan.alan] = alan.sebep;
  }
  return cikti;
}

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
