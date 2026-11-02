import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * Tanımsız token sessizce kayboluyor: `var(--bosluk-5)` hiçbir hata
 * vermeden boş değere düşüyor ve kart iç boşluksuz kalıyor. Böyle iki
 * token aylarca ekranları bozdu; bu kapı onu bir daha yakalar.
 */
function dosyalar(dizin: string, uzanti: string[]): string[] {
  return readdirSync(dizin, { withFileTypes: true }).flatMap((kayit) => {
    const yol = join(dizin, kayit.name);
    if (kayit.isDirectory()) return dosyalar(yol, uzanti);
    // Test dosyasi atlanir: aciklamasinda gecen token adi kullanim degil.
    if (kayit.name.includes('.test.')) return [];
    return uzanti.some((u) => kayit.name.endsWith(u)) ? [yol] : [];
  });
}

const STIL = ['src/styles/tokens.css', 'src/styles/bilesenler.css']
  .map((yol) => readFileSync(yol, 'utf-8'))
  .join('\n');

const TANIMLI = new Set(Array.from(STIL.matchAll(/^\s*(--[a-z0-9-]+):/gm), (e) => e[1]));

describe('tasarım token’ları', () => {
  it('kodda kullanılan her token tanımlı', () => {
    const eksik = new Map<string, string[]>();

    for (const yol of dosyalar('src', ['.tsx', '.ts', '.css'])) {
      for (const eslesme of readFileSync(yol, 'utf-8').matchAll(/var\((--[a-z0-9-]+)\)/g)) {
        const ad = eslesme[1];
        if (!TANIMLI.has(ad)) eksik.set(ad, [...(eksik.get(ad) ?? []), yol]);
      }
    }

    expect(Object.fromEntries(eksik)).toEqual({});
  });

  it('tanımlı her token kullanılıyor', () => {
    // Kullanılmayan token, uygulanmamış tasarım kararıdır: ya ekrana
    // geçer ya listeden düşer.
    const kod = dosyalar('src', ['.tsx', '.ts', '.css'])
      .map((yol) => readFileSync(yol, 'utf-8'))
      .join('\n');

    const kullanilmayan = [...TANIMLI].filter((ad) => !kod.includes(`var(${ad})`));

    expect(kullanilmayan).toEqual([]);
  });
});
