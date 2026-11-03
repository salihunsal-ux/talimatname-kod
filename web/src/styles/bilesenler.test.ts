import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const BILESEN = readFileSync('src/styles/bilesenler.css', 'utf-8');

/** Yorumlar çıkarılır: içlerinde sınıf adı gibi görünen metin geçiyor. */
const YORUMSUZ = BILESEN.replace(/\/\*[\s\S]*?\*\//g, '');

/** Seçici metni (süslü parantezden önceki kısım), @media içindekiler dâhil. */
const SECICILER = Array.from(YORUMSUZ.matchAll(/([^{}]+)\{/g), (e) => e[1].trim());

/** En dış düzeydeki kurallar: @media içindekiler girintili olduğu için düşer. */
const UST_DUZEY = Array.from(YORUMSUZ.matchAll(/^([^\s@}][^{]*)\{/gm), (e) => e[1].trim());

function dosyalar(dizin: string): string[] {
  return readdirSync(dizin, { withFileTypes: true }).flatMap((kayit) => {
    const yol = join(dizin, kayit.name);
    if (kayit.isDirectory()) return dosyalar(yol);
    return /\.tsx?$/.test(kayit.name) ? [yol] : [];
  });
}

/**
 * `Dugme` ve `Kart` sınıf adını şablon dizgesinden kuruyor
 * (`dugme--${gorunum}`), yani ad kodda düz metin olarak geçmiyor.
 */
const URETILEN = new Set([
  'dugme--birincil',
  'dugme--ikincil',
  'dugme--sessiz',
  'dugme--kucuk',
  'dugme--tam',
  'kart--yuzen',
  'ozet-kutu--uyari',
  'ozet-kutu--kritik',
  // Yalnızca pano ızgarasında, `durum--${g.durum}` ile.
  'durum--bos',
]);

describe('bileşen katmanı', () => {
  it('tanımlı her sınıf kullanılıyor', () => {
    // Ölü sınıf, uygulanmamış bir tasarım kararıdır — ya da daha
    // kötüsü, ekranın satır içinde ezdiği bir kural. `.giris-sayilar`
    // tam da böyleydi: sayı çiftleri (dl) için yazılmış, ekranda bir
    // liste duruyordu ve ölçülerini satır içi stil belirliyordu.
    const kod = dosyalar('src')
      .map((yol) => readFileSync(yol, 'utf-8'))
      .join('\n');

    const siniflar = new Set<string>();
    for (const secici of SECICILER) {
      for (const esl of secici.matchAll(/\.([a-zA-Z][a-zA-Z0-9_-]*)/g)) siniflar.add(esl[1]);
    }

    const kullanilmayan = [...siniflar]
      .filter((ad) => !URETILEN.has(ad))
      .filter((ad) => !kod.includes(ad));

    expect(kullanilmayan).toEqual([]);
  });

  it('yığın sıfırlaması dosyanın son kuralı', () => {
    // Aynı özgüllükte sonra gelen tanım kazanıyor: `.yigin > *` bir
    // bileşenin kendi kenar boşluğunu ezmek için var, dolayısıyla
    // hepsinden sonra gelmeli. Yukarı taşınırsa hata vermez, susar —
    // dar ekran çip kuralında bir kez böyle olmuştu.
    expect(UST_DUZEY.at(-1)).toBe('.yigin > *');
  });
});
