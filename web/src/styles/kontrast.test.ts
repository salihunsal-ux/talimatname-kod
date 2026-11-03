import { readFileSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

/**
 * NFR-11: metin ile zemini arasında en az 4,5:1.
 *
 * Bu sayıyı elle doğrulamak işe yaramadı — üç çift aylarca altında
 * kaldı (uyarı çipi 3,07:1) ve kimse fark etmedi, çünkü renkler
 * "yakışıyordu". Çiftler burada yazılı, değerler token dosyasından
 * okunuyor: bir token değişirse ölçü burada düşer.
 */
const TOKEN = readFileSync('src/styles/tokens.css', 'utf-8');

/** `:root { … }` ve koyu tema bloğu ayrı ayrı okunur. */
function blok(baslangic: string): Record<string, string> {
  const i = TOKEN.indexOf(baslangic);
  if (i < 0) throw new Error(`blok bulunamadı: ${baslangic}`);
  const govde = TOKEN.slice(i + baslangic.length, TOKEN.indexOf('\n}', i));
  return Object.fromEntries(
    Array.from(govde.matchAll(/--renk-([a-z0-9-]+):\s*(#[0-9a-f]{6})/g), (e) => [e[1], e[2]]),
  );
}

const ACIK = blok(':root {');
const KOYU = blok(":root[data-tema='koyu'] {");
/** Aynı palet bir de medya sorgusunda yazılı; ikisi ayrışabilir. */
const KOYU_MEDYA = blok(":root:not([data-tema='acik']) {");

function parlaklik(renk: string): number {
  const kanal = [1, 3, 5].map((i) => parseInt(renk.slice(i, i + 2), 16) / 255);
  const [r, g, b] = kanal.map((x) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function kontrast(yazi: string, zemin: string): number {
  const [a, b] = [parlaklik(yazi), parlaklik(zemin)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

/**
 * Ekranda gerçekten yan yana duran çiftler. Kaynak: bilesenler.css'te
 * hem `color` hem `background` veren kurallar.
 */
const CIFTLER: [ad: string, yazi: string, zemin: string][] = [
  ['durum çipi · marka', 'marka', 'marka-acik'],
  ['durum çipi · kritik', 'kritik', 'kritik-acik'],
  ['durum çipi · uyarı', 'uyari', 'uyari-acik'],
  ['durum çipi · pasif', 'sessiz', 'yuzey2'],
  ['durum çipi · nötr', 'murekkep2', 'yuzey2'],
  ['seçili düğme · menü · seçim çipi', 'marka', 'marka-acik'],
  ['bildiri · sağlam', 'murekkep', 'marka-acik'],
  ['bildiri · uyarı', 'murekkep', 'uyari-acik'],
  ['bildiri · hata', 'kritik', 'kritik-acik'],
  ['bildiri · nötr', 'murekkep2', 'yuzey2'],
  ['birincil düğme', 'birincil-yazi', 'birincil-zemin'],
  ['üst bant · yardımcı', 'koyu-sessiz', 'koyu'],
  ['üst bant · vurgu', 'koyu-marka', 'koyu'],
  ['gövde metni', 'murekkep', 'zemin'],
  ['ikincil metin', 'murekkep2', 'zemin'],
  ['yardımcı metin', 'sessiz', 'zemin'],
  ['uyarı metni', 'uyari', 'yuzey'],
  ['hata metni', 'kritik', 'yuzey'],
  ['bağlantı', 'marka', 'yuzey'],
  ['alan metni', 'murekkep', 'yuzey2'],
  ['kanıt yeri', 'sessiz', 'yuzey2'],
];

describe.each([
  ['açık tema', ACIK],
  ['koyu tema', KOYU],
])('%s', (_ad, tema) => {
  it.each(CIFTLER)('%s en az 4,5:1', (_cift, yazi, zemin) => {
    // Yuvarlanmış değer: hata mesajı "expected 3.07 to be greater than
    // or equal to 4.5" diyor, yani düzeltmek için gereken tek bilgi
    // zaten mesajda.
    const olculen = Number(kontrast(tema[yazi], tema[zemin]).toFixed(2));
    expect(olculen).toBeGreaterThanOrEqual(4.5);
  });
});

describe('token okuma', () => {
  it('iki tema da aynı renk adlarını tanımlıyor', () => {
    // Koyu temada eksik kalan bir ad, açık temanınkini miras alır ve
    // koyu zeminde okunmaz. Eksikliği burada görelim.
    expect(Object.keys(KOYU).sort()).toEqual(Object.keys(ACIK).sort());
  });

  it('koyu palet iki yerde aynı yazılı', () => {
    // Palet hem `[data-tema='koyu']` hem de `prefers-color-scheme`
    // bloğunda duruyor; düz CSS'te bunu tek kaynağa indiremiyoruz.
    // En azından ayrışmasınlar: elle düzeltilen bir değer öbürüne
    // yazılmayı unutulabilir.
    expect(KOYU_MEDYA).toEqual(KOYU);
  });
});

describe('koyu çapa yüzeyi', () => {
  // Yön C'nin fikri: sayfanın bir **ağırlık merkezi** var — üst bant,
  // giriş paneli, pano manşeti. Açık temada bu yüzeyin kendisinden
  // geliyor (15,3:1). Koyu temada sayfa da koyu olduğu için yüzeyle
  // ayrılamıyor (1,19:1); ayrım kenardan gelmek zorunda.
  it.each([
    ['açık tema', ACIK],
    ['koyu tema', KOYU],
  ])('%s: çapa ya yüzeyiyle ya kenarıyla sayfadan ayrılıyor', (_ad, tema) => {
    const yuzeyle = kontrast(tema['koyu'], tema['zemin']);
    const kenarla = kontrast(tema['koyu-cizgi'], tema['koyu']);
    expect(yuzeyle >= 3 || kenarla >= 1.25).toBe(true);
  });
});
