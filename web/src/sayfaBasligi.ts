/**
 * Sekme başlığını açık ekrana göre yazar.
 *
 * Tek sayfalık uygulamada `document.title` kendiliğinden değişmiyor:
 * on bir ekranın hepsi "Talimatname · Yönetim paneli" diyordu ve saha
 * istemcisi de aynı başlığı taşıyordu — orası yönetim paneli değil.
 * Sekme değiştiren ya da ekran okuyucu kullanan kişi nerede olduğunu
 * başlıktan anlayabilmeli (bağımsız test turu D-2).
 */

import { tr } from './i18n/tr';

/** Kapıya göre uygulama adı: panel ile saha istemcisi aynı şey değil. */
export function uygulamaAdi(saha: boolean): string {
  return saha ? tr.uygulama.sahaBaslik : tr.uygulama.panelBaslik;
}

export function sayfaBasligiYaz(ekran: string | null, saha: boolean): void {
  const taban = `${tr.uygulama.ad} · ${uygulamaAdi(saha)}`;
  document.title = ekran ? `${ekran} · ${taban}` : taban;
}
