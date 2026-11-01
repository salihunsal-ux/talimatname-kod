/**
 * Rapor veri erişimi (ST-090; FR-1207, FR-1208, FR-1220).
 *
 * Kapsam süzgeci sunucuda: bölge müdürü bölgesini, şube müdürü
 * şubesini görüyor. Panel kapsam hesaplamıyor.
 */
import { api } from './client';
import { pdfSonucu, type PdfSonucu } from './ciktilar';
import type { components } from './schema';

export type AylikOzet = components['schemas']['AylikOzet'];
export type SubeOzeti = components['schemas']['SubeOzeti'];
export type OlcumSerisi = components['schemas']['OlcumSerisi'];
export type GaleriKanidi = components['schemas']['GaleriKanidi'];

export async function aylikOzet(yil: number, ay: number): Promise<AylikOzet> {
  const { data, error } = await api.GET('/api/v1/reports/monthly', {
    params: { query: { year: yil, month: ay } },
  });
  if (error) throw error;
  return data;
}

export async function olcumGunlugu(
  ilkGun: string,
  sonGun: string,
  yalnizAralikDisi = false,
): Promise<OlcumSerisi[]> {
  const { data, error } = await api.GET('/api/v1/reports/measurements', {
    params: {
      query: { first_day: ilkGun, last_day: sonGun, only_out_of_range: yalnizAralikDisi },
    },
  });
  if (error) throw error;
  return data;
}

/**
 * Aylık özetin PDF'i (FR-1220). Belirteç `api.use` ara katmanından
 * geliyor: `<a href>` ile indirmek belirteci URL'ye koymak ya da
 * kanıt bağlantısı gibi ikinci bir imza düzeni kurmak demek olurdu.
 *
 * Eşiği geçen dönemde sunucu dosya yerine **iş kaydı** dönüyor
 * (202, FR-1217); sonuç iki hâli de taşıyor.
 */
export async function aylikOzetPdf(yil: number, ay: number): Promise<PdfSonucu> {
  const { data, error, response } = await api.GET('/api/v1/reports/monthly.pdf', {
    params: { query: { year: yil, month: ay } },
    parseAs: 'blob',
  });
  if (error) throw error;
  return pdfSonucu(data, response.status);
}

/** Ölçüm günlüğünün PDF'i (FR-1214) — denetçiye verilen kâğıt. */
export async function olcumGunluguPdf(
  ilkGun: string,
  sonGun: string,
  yalnizAralikDisi = false,
): Promise<PdfSonucu> {
  const { data, error, response } = await api.GET('/api/v1/reports/measurements.pdf', {
    params: {
      query: { first_day: ilkGun, last_day: sonGun, only_out_of_range: yalnizAralikDisi },
    },
    parseAs: 'blob',
  });
  if (error) throw error;
  return pdfSonucu(data, response.status);
}

/**
 * Blob'u kullanıcıya indirir. Nesne URL'si hemen geri veriliyor:
 * bırakılmış URL sekme kapanana kadar belleği tutar.
 */
export function dosyayiIndir(blob: Blob, dosyaAdi: string): void {
  const url = URL.createObjectURL(blob);
  const bag = document.createElement('a');
  bag.href = url;
  bag.download = dosyaAdi;
  document.body.appendChild(bag);
  bag.click();
  bag.remove();
  URL.revokeObjectURL(url);
}

export async function kanitGalerisi(
  ilkGun: string,
  sonGun: string,
  yalnizBayrakli = false,
): Promise<GaleriKanidi[]> {
  const { data, error } = await api.GET('/api/v1/reports/gallery', {
    params: { query: { first_day: ilkGun, last_day: sonGun, only_flagged: yalnizBayrakli } },
  });
  if (error) throw error;
  return data;
}
