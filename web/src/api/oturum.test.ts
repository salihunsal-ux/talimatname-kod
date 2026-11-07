import { afterEach, describe, expect, it, vi } from 'vitest';

import { belirtecAl, belirtecYaz, oturumDinle, oturumDustu } from './oturum';
import { sorguIstemcisi } from './sorguIstemcisi';

/** Sunucunun oturum reddi (RFC 9457); davranış `type`a bakıyor. */
const REDDEDILDI = {
  type: 'urn:talimatname:belirtec-gecersiz',
  title: 'Oturum geçersiz ya da süresi doldu',
  status: 403,
};

afterEach(() => {
  belirtecYaz(null);
  sorguIstemcisi.clear();
});

describe('oturum düşüşü', () => {
  it('belirteci bırakıyor ve bir kez duyuruyor', () => {
    belirtecYaz('eski-belirtec');
    const dinleyici = vi.fn();
    const birak = oturumDinle(dinleyici);

    oturumDustu();

    expect(belirtecAl()).toBeNull();
    expect(dinleyici).toHaveBeenCalledTimes(1);
    birak();
  });

  it('aynı turda ikinci kez duyurmuyor', () => {
    // Süre dolunca birkaç sorgu birden 403 alıyor ve her biri burayı
    // çağırıyor; giriş ekranı bir kez açılmalı.
    belirtecYaz('eski-belirtec');
    const dinleyici = vi.fn();
    const birak = oturumDinle(dinleyici);

    oturumDustu();
    oturumDustu();

    expect(dinleyici).toHaveBeenCalledTimes(1);
    birak();
  });

  it('abonelik bırakılınca haber gitmiyor', () => {
    belirtecYaz('eski-belirtec');
    const dinleyici = vi.fn();
    oturumDinle(dinleyici)();

    oturumDustu();

    expect(dinleyici).not.toHaveBeenCalled();
  });
});

describe('sorgu önbelleği', () => {
  it('sunucu oturumu reddedince oturumu düşürüyor', async () => {
    // Asıl bağ bu: ekranlar hatayı kendileri karşılamıyor, önbellek
    // karşılıyor. Kopsaydı kullanıcı ölü bir panelde kalırdı.
    belirtecYaz('eski-belirtec');
    const dinleyici = vi.fn();
    const birak = oturumDinle(dinleyici);

    await expect(
      sorguIstemcisi.fetchQuery({
        queryKey: ['deneme-reddedildi'],
        queryFn: () => Promise.reject(REDDEDILDI),
        retry: false,
      }),
    ).rejects.toBeDefined();

    expect(belirtecAl()).toBeNull();
    expect(dinleyici).toHaveBeenCalledTimes(1);
    birak();
  });

  it('başka hatada oturuma dokunmuyor', async () => {
    belirtecYaz('saglam-belirtec');
    const dinleyici = vi.fn();
    const birak = oturumDinle(dinleyici);

    await expect(
      sorguIstemcisi.fetchQuery({
        queryKey: ['deneme-sunucu-hatasi'],
        queryFn: () =>
          Promise.reject({ type: 'urn:talimatname:gecersiz-istek', title: 'Olmadı', status: 400 }),
        retry: false,
      }),
    ).rejects.toBeDefined();

    expect(belirtecAl()).toBe('saglam-belirtec');
    expect(dinleyici).not.toHaveBeenCalled();
    birak();
  });
});

/**
 * Sessiz yenileme (FR-0203).
 *
 * Modüller her testte yeniden yükleniyor: istemcinin taban adresi
 * `import.meta.env` okunurken bir kez belirleniyor ve jsdom'da göreli
 * adresle `Request` kurulamıyor (bkz. `dogrulama.test.ts`).
 */
async function oturumModulu() {
  vi.stubEnv('VITE_API_URL', 'http://panel.test');
  vi.resetModules();
  return import('./oturum');
}

describe('sessiz yenileme (FR-0203)', () => {
  const YENILEME = 'talimatname.yenileme';
  const SONERME = 'talimatname.sonerme';
  const gercekFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = gercekFetch;
    localStorage.clear();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  function oturumKur(kalanMs: number): void {
    localStorage.setItem('talimatname.belirtec', 'eski-erisim');
    localStorage.setItem(YENILEME, 'eski-yenileme');
    localStorage.setItem(SONERME, String(Date.now() + kalanMs));
  }

  function yanit(govde: unknown, durum = 200): Response {
    return new Response(JSON.stringify(govde), {
      status: durum,
      headers: { 'content-type': 'application/json' },
    });
  }

  const YENI_OTURUM = {
    access_token: 'yeni-erisim',
    token_type: 'bearer',
    expires_in_minutes: 15,
    refresh_token: 'yeni-yenileme',
    refresh_expires_at: '2026-11-09T09:00:00Z',
    user: { id: 'k1', full_name: 'Cem', phone: null, roles: [] },
  };

  it('süresi yaklaşan belirteci tazeliyor ve yenisini saklıyor', async () => {
    oturumKur(10_000); // 10 sn kaldı; pay 60 sn
    const getir = vi.fn().mockResolvedValue(yanit(YENI_OTURUM));
    globalThis.fetch = getir;
    const { tazele, belirtecAl: oku, yenilemeBelirteciAl: yenileme } = await oturumModulu();

    expect(await tazele()).toBe(true);

    expect(oku()).toBe('yeni-erisim');
    expect(yenileme()).toBe('yeni-yenileme');
    // Yenileme belirteci **gövdede** gidiyor, Authorization başlığında değil.
    const istek = getir.mock.calls[0][0] as Request;
    expect(istek.url).toContain('/auth/refresh');
    expect(await istek.clone().json()).toEqual({ refresh_token: 'eski-yenileme' });
    expect(istek.headers.get('Authorization')).toBeNull();
  });

  it('yenileme reddedilirse oturum düşüyor', async () => {
    // Çalınmış belirteç zinciri düşürdüyse sunucu 403 verir; kullanıcıyı
    // 403 duvarına koşturmaktansa giriş ekranına almak dürüst.
    oturumKur(10_000);
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(yanit({ type: 'urn:talimatname:oturum-gecersiz' }, 403));
    const modul = await oturumModulu();
    const dinleyici = vi.fn();
    const birak = modul.oturumDinle(dinleyici);

    expect(await modul.tazele()).toBe(false);

    expect(modul.belirtecAl()).toBeNull();
    expect(modul.yenilemeBelirteciAl()).toBeNull();
    expect(dinleyici).toHaveBeenCalledTimes(1);
    birak();
  });

  it('yenileme belirteci yoksa denemiyor', async () => {
    localStorage.setItem('talimatname.belirtec', 'erisim');
    const getir = vi.fn();
    globalThis.fetch = getir;
    const { tazele } = await oturumModulu();

    expect(await tazele()).toBe(false);
    expect(getir).not.toHaveBeenCalled();
  });

  it('aynı anda gelen çağrılar tek istek yapıyor', async () => {
    // Beş sorgu birden dönünce beş yenileme isteği gitmesin.
    oturumKur(10_000);
    const getir = vi.fn().mockResolvedValue(yanit(YENI_OTURUM));
    globalThis.fetch = getir;
    const { tazele } = await oturumModulu();

    await Promise.all([tazele(), tazele(), tazele()]);

    expect(getir).toHaveBeenCalledTimes(1);
  });

  it('çıkış yenileme belirtecini sunucuda da iptal ediyor', async () => {
    oturumKur(600_000);
    const getir = vi.fn().mockResolvedValue(yanit({ ok: true }));
    globalThis.fetch = getir;
    const modul = await oturumModulu();

    await modul.cikisYap();

    expect(getir).toHaveBeenCalledTimes(1);
    expect((getir.mock.calls[0][0] as Request).url).toContain('/auth/logout');
    expect(modul.belirtecAl()).toBeNull();
    expect(modul.yenilemeBelirteciAl()).toBeNull();
  });

  it('sunucuya ulaşılamasa da yerelden siliniyor', async () => {
    oturumKur(600_000);
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('ağ yok'));
    const modul = await oturumModulu();

    await modul.cikisYap();

    expect(modul.belirtecAl()).toBeNull();
    expect(modul.yenilemeBelirteciAl()).toBeNull();
  });
});
