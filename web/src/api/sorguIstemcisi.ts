import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';

import { problemCoz } from './client';
import { oturumDustu } from './oturum';

/** Sunucunun oturum reddi; davranış `type`a bakar, başlık metnine değil. */
const OTURUM_GECERSIZ = 'urn:talimatname:belirtec-gecersiz';

/**
 * Oturum düştüyse ekranda kalmanın anlamı yok: bundan sonraki her
 * istek de reddedilir. Belirteci burada bırakıyoruz, giriş ekranına
 * dönmeyi `App` üstleniyor.
 */
function oturumuSina(hata: unknown): void {
  if (problemCoz(hata)?.type === OTURUM_GECERSIZ) oturumDustu();
}

/**
 * Sunucu durumu önbelleği. Ayrı dosyada: bileşen dosyaları yalnızca
 * bileşen dışa aktarır (react-refresh kuralı).
 */
export const sorguIstemcisi = new QueryClient({
  queryCache: new QueryCache({ onError: oturumuSina }),
  mutationCache: new MutationCache({ onError: oturumuSina }),
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});
