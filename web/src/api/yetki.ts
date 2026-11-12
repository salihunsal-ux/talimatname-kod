/**
 * Arayüz tarafında rol kapısı (FR-0205).
 *
 * Bu **güvenlik değil, nezakettir**: asıl denetim sunucuda. Buradaki
 * tek amaç, kullanıcıya açamayacağı bir bölümü ya da basamayacağı bir
 * düğmeyi göstermemek — 403 görmek bilgi değil, sürtünmedir.
 */
import { createContext, use } from 'react';

import type { Ben } from './oturum';

export type Rol = 'admin' | 'region_manager' | 'auditor' | 'branch_manager' | 'staff';

/**
 * Roller ve kapsamları — **tek liste**. Önce personel sayfasının
 * içinde duruyordu; plan editörü de rol seçtirmeye başlayınca ikinci
 * kopya çıkacaktı ve iki liste zamanla ayrışırdı.
 */
export const ROLLER: { deger: Rol; etiket: string; kapsam: 'yok' | 'bolge' | 'sube' }[] = [
  { deger: 'admin', etiket: 'Yönetici', kapsam: 'yok' },
  { deger: 'region_manager', etiket: 'Bölge müdürü', kapsam: 'bolge' },
  // Denetçi de bölge kapsamlı: şubeye gider ama şubeye bağlı değil.
  { deger: 'auditor', etiket: 'Denetçi', kapsam: 'bolge' },
  { deger: 'branch_manager', etiket: 'Şube müdürü', kapsam: 'sube' },
  { deger: 'staff', etiket: 'Personel', kapsam: 'sube' },
];

/**
 * Listeyi **yapan** roller (sunucudaki `WORKER_ROLES` ile aynı küme).
 * Yönetici ve bölge müdürü her şubeyi görür ama orada çalışmaz;
 * plana onları atamak, hatırlatmayı yapmayacak kişiye göndermektir.
 */
export const CALISAN_ROLLERI: Rol[] = ['branch_manager', 'staff'];

export function rolEtiketi(rol: string): string {
  return ROLLER.find((r) => r.deger === rol)?.etiket ?? rol;
}

export const OturumBaglami = createContext<Ben | null>(null);

export function useBen(): Ben | null {
  return use(OturumBaglami);
}

export function rolleri(ben: Ben | null): Rol[] {
  return (ben?.roles ?? []).map((atama) => atama.role as Rol);
}

export function rolVar(ben: Ben | null, ...aranan: Rol[]): boolean {
  const sahip = rolleri(ben);
  return aranan.some((rol) => sahip.includes(rol));
}

/**
 * Panelin okuma ekranlarını açabilen roller.
 *
 * Sunucu da aynı kümeyi istiyor (`guvenlik.Gozlemci`); burada tutmanın
 * sebebi personele kapalı kapıyı göstermemek. Personelin ekranı mobil
 * uygulamada (ADR-0013 Faz B).
 *
 * Denetçi listede: şubeye gidip denetim listesini kendisi dolduruyor,
 * bunun için şube ağacını, panoyu ve raporları görmesi gerekiyor.
 * Karar verme yetkisi ayrı (`yoneticiMi`).
 */
export function mudurMu(ben: Ben | null): boolean {
  return rolVar(ben, 'admin', 'region_manager', 'branch_manager', 'auditor');
}

/** Yazma yetkisi olan tek rol: yönetici (ST-005). */
export function yoneticiMi(ben: Ben | null): boolean {
  return rolVar(ben, 'admin');
}

export function useYonetici(): boolean {
  return yoneticiMi(useBen());
}
