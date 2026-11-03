import { readFileSync } from 'node:fs';

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TEMA_ANAHTARI, temaOku, temaUygula, temaYaz } from './tema';

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-tema');
  document.documentElement.style.removeProperty('color-scheme');
});

describe('tema', () => {
  it('seçim yokken sistemi izler', () => {
    expect(temaOku()).toBe('sistem');

    temaUygula('sistem');
    expect(document.documentElement.hasAttribute('data-tema')).toBe(false);
    expect(document.documentElement.style.colorScheme).toBe('');
  });

  it('seçim `data-tema` ile yazılıyor ve kalıcı', () => {
    temaYaz('koyu');

    expect(document.documentElement.getAttribute('data-tema')).toBe('koyu');
    expect(localStorage.getItem(TEMA_ANAHTARI)).toBe('koyu');
    expect(temaOku()).toBe('koyu');
  });

  it('sisteme dönünce kayıt siliniyor', () => {
    temaYaz('acik');
    temaYaz('sistem');

    expect(localStorage.getItem(TEMA_ANAHTARI)).toBeNull();
    expect(document.documentElement.hasAttribute('data-tema')).toBe(false);
  });

  it('tarayıcı denetimleri de temaya uyuyor', () => {
    // `color-scheme` yazılmazsa sayfa açık, içindeki tarih seçici koyu
    // açılır: kullanıcı iki temayı aynı ekranda görür.
    temaYaz('acik');
    expect(document.documentElement.style.colorScheme).toBe('light');

    temaYaz('koyu');
    expect(document.documentElement.style.colorScheme).toBe('dark');
  });

  it('depolama kapalıyken uygulama durmuyor', () => {
    // Gizli sekmede erişim hata atıyor. Tema seçilemiyor olabilir;
    // sayfanın açılmaması kabul edilemez.
    const patla = () => {
      throw new Error('depolama kapalı');
    };
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(patla);
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(patla);

    expect(temaOku()).toBe('sistem');
    expect(() => temaYaz('koyu')).not.toThrow();
    // Seçim bu oturumda yine de geçerli: yalnızca kalıcı değil.
    expect(document.documentElement.getAttribute('data-tema')).toBe('koyu');

    vi.restoreAllMocks();
  });

  it('açılış betiği modülle aynı anahtarı okuyor', () => {
    // index.html'deki betik tema'yı ilk boyamadan önce uyguluyor ve
    // mantığı burada bir kez daha yazılı. İkisi ayrışırsa kullanıcı
    // seçtiği temanın tersini bir an görür — sessiz bir kusur.
    const html = readFileSync('index.html', 'utf-8');

    expect(html).toContain(TEMA_ANAHTARI);
    expect(html).toContain('data-tema');
    expect(html).toContain('colorScheme');
  });
});
