import { QueryClient } from '@tanstack/react-query';

/**
 * Sunucu durumu önbelleği. Ayrı dosyada: bileşen dosyaları yalnızca
 * bileşen dışa aktarır (react-refresh kuralı).
 */
export const sorguIstemcisi = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});
