import { afterEach, describe, expect, it } from 'vitest';

import { sayfaBasligiYaz, uygulamaAdi } from './sayfaBasligi';

/**
 * Bağımsız test turu D-2: on bir ekranın hepsi aynı başlığı taşıyordu
 * ve saha istemcisi de "Yönetim paneli" diyordu — orası yönetim paneli
 * değil.
 */
afterEach(() => {
  document.title = '';
});

describe('sayfa başlığı', () => {
  it('iki kapıya iki ad veriyor', () => {
    expect(uygulamaAdi(false)).toBe('Yönetim paneli');
    expect(uygulamaAdi(true)).toBe('Saha');
  });

  it('açık ekranı başlığa yazıyor', () => {
    sayfaBasligiYaz('Raporlar', false);

    expect(document.title).toBe('Raporlar · Talimatname · Yönetim paneli');
  });

  it('ekran verilmezse yalnızca uygulama adını yazıyor', () => {
    sayfaBasligiYaz(null, true);

    expect(document.title).toBe('Talimatname · Saha');
  });

  it('saha kapısı "Yönetim paneli" demiyor', () => {
    sayfaBasligiYaz(null, true);

    expect(document.title).not.toContain('Yönetim paneli');
  });

  it('ekran değişince başlık da değişiyor', () => {
    sayfaBasligiYaz('Pano', false);
    const ilk = document.title;
    sayfaBasligiYaz('Planlar', false);

    expect(document.title).not.toBe(ilk);
    expect(document.title).toContain('Planlar');
  });
});
