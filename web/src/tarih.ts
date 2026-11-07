/**
 * Tarih yardımcıları.
 *
 * `toISOString().slice(0, 10)` **UTC** gün verir: İstanbul'da 8 Kasım
 * 00:30, UTC'de hâlâ 7 Kasım 21:30'dur. Pano varsayılan iş gününü,
 * plan başlangıcını ve rapor aralığını böyle hesaplıyordu; gece yarısı
 * ile 03:00 arasında hepsi bir gün geriye düşüyordu (bağımsız test
 * turu B11). Plan başlangıcında etkisi en ağırı: plan dünden başlamış
 * görünüyordu.
 *
 * Burada gün **yerel** saatten kuruluyor. İş gününün şube saat
 * dilimine göre belirlenmesi (BR-01) sunucunun işi; panel tek bir gün
 * seçtiği için en doğru varsayılan, bakan kişinin günü.
 */

/** Verilen anın yerel günü, `YYYY-MM-DD`. */
export function gunIso(an: Date = new Date()): string {
  const yil = an.getFullYear();
  const ay = String(an.getMonth() + 1).padStart(2, '0');
  const gun = String(an.getDate()).padStart(2, '0');
  return `${yil}-${ay}-${gun}`;
}

/** Bugünün yerel günü, `YYYY-MM-DD`. */
export function bugunIso(): string {
  return gunIso();
}

/** `gunSayisi` gün öncesinden bugüne kapalı aralık (ikisi de yerel gün). */
export function sonGunler(gunSayisi: number): { ilk: string; son: string } {
  const son = new Date();
  const ilk = new Date(son.getTime() - gunSayisi * 24 * 60 * 60 * 1000);
  return { ilk: gunIso(ilk), son: gunIso(son) };
}
