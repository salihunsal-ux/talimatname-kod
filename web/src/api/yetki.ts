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
