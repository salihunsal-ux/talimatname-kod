/**
 * Tema seçimi: sistem · açık · koyu.
 *
 * Token'lar iki yoldan devreye giriyor — `prefers-color-scheme` medya
 * sorgusu (sistem) ve `:root[data-tema]` (kullanıcı seçimi). İkincisi
 * tanımlıydı ama hiçbir şey yazmıyordu, yani koyu tema yalnızca
 * işletim sistemi tercihini izliyordu. Aydınlık bir mutfakta koyu
 * cihaz kullanan şube müdürünün açık temaya geçmesi gerekebiliyor.
 */
export type Tema = 'sistem' | 'acik' | 'koyu';

/** index.html'deki açılış betiği de bunu okuyor (bkz. tema.test.ts). */
export const TEMA_ANAHTARI = 'talimatname.tema';

export const TEMALAR: Tema[] = ['sistem', 'acik', 'koyu'];

function gecerli(deger: string | null): Tema {
  return deger === 'acik' || deger === 'koyu' ? deger : 'sistem';
}

export function temaOku(): Tema {
  try {
    return gecerli(localStorage.getItem(TEMA_ANAHTARI));
  } catch {
    // Gizli sekmede ya da depolama kapalıyken erişim hata atıyor:
    // tema seçilememesi uygulamayı durdurmamalı.
    return 'sistem';
  }
}

export function temaUygula(tema: Tema): void {
  const kok = document.documentElement;
  if (tema === 'sistem') {
    kok.removeAttribute('data-tema');
    kok.style.removeProperty('color-scheme');
    return;
  }
  kok.setAttribute('data-tema', tema);
  // Tarayıcının kendi denetimleri — tarih seçici, açılır liste,
  // kaydırma çubuğu — `color-scheme`e bakıyor. Yazmazsak kullanıcı
  // açık temayı seçse de takvim koyu açılır: sayfa bir tema,
  // içindeki takvim başka tema olur.
  kok.style.colorScheme = tema === 'koyu' ? 'dark' : 'light';
}

export function temaYaz(tema: Tema): void {
  try {
    if (tema === 'sistem') localStorage.removeItem(TEMA_ANAHTARI);
    else localStorage.setItem(TEMA_ANAHTARI, tema);
  } catch {
    // Seçim bu oturumda geçerli olur, kalıcı olmaz.
  }
  temaUygula(tema);
}
