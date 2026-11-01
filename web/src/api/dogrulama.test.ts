import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * Açık sayfa kimlik bilgisi taşımamalı (FR-1218).
 *
 * Kural `api/oturum.ts`deki ara katmanda duruyor ve gözle görülmüyor:
 * tarayıcıda eski bir belirteç varken doğrulama isteğinin başlığı
 * taşımadığını ancak böyle bir test tutar.
 *
 * Modüller her testte yeniden yükleniyor: istemcinin taban adresi
 * `import.meta.env` okunurken bir kez belirleniyor ve jsdom'da
 * göreli adresle `Request` kurulamıyor.
 */
async function modul() {
  vi.stubEnv('VITE_API_URL', 'http://panel.test');
  vi.resetModules();
  const [{ belgeDogrula }, { belirtecYaz }] = await Promise.all([
    import('./dogrulama'),
    import('./oturum'),
  ]);
  return { belgeDogrula, belirtecYaz };
}

describe('belgeDogrula', () => {
  const gercekFetch = globalThis.fetch;
  let istekler: Request[] = [];

  beforeEach(() => {
    istekler = [];
    globalThis.fetch = vi.fn(async (istek: unknown) => {
      istekler.push(istek as Request);
      return new Response(JSON.stringify({ code: 'A1B2-C3D4-E5F6' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    }) as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = gercekFetch;
    vi.unstubAllEnvs();
    localStorage.clear();
  });

  it('oturum açıkken bile belirteç göndermez', async () => {
    const { belgeDogrula, belirtecYaz } = await modul();
    belirtecYaz('ornek-belirtec');

    await belgeDogrula('A1B2-C3D4-E5F6');

    expect(istekler).toHaveLength(1);
    expect(istekler[0].headers.get('Authorization')).toBeNull();
  });

  it('kodu yola koyar', async () => {
    const { belgeDogrula } = await modul();

    await belgeDogrula('A1B2-C3D4-E5F6');

    expect(new URL(istekler[0].url).pathname).toBe('/api/v1/verify/A1B2-C3D4-E5F6');
  });
});
