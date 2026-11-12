import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Geliştirmede panel API'yi **kendi kaynağından** çağırır: Vite `/api`
// isteklerini backend'e aktarır. Böylece CORS geliştirme sorunu olmaktan
// çıkar (API'deki CORS ayarı dağıtılmış ortamlar için duruyor) ve port
// değişince yalnızca burası güncellenir.
const API_HEDEFI = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8020';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: API_HEDEFI, changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    // Gün kesimi **yerel** saate göre yapılıyor (BR-01, `src/tarih.ts`).
    // CI UTC'de koşuyor, yani İstanbul'un bir gün ileride olduğu
    // saatleri hiç görmüyordu: gece yarısı testi yerelde geçip CI'da
    // kırıldı. Ürün Türkiye'de çalışıyor; test de o saatte koşsun.
    env: { TZ: 'Europe/Istanbul' },
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
    coverage: { reporter: ['text'], include: ['src/**/*.{ts,tsx}'] },
  },
});
