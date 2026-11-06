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
