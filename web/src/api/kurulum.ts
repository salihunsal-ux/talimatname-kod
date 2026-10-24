/**
 * Kurulum sihirbazı veri erişimi (ST-008; FR-1401, FR-0105).
 *
 * Excel yükleme ve indirme `openapi-fetch` üzerinden gitmiyor: biri
 * multipart, diğeri ikili dosya. Belirteci elle ekliyoruz — tek yer
 * burası, bileşenler yine taşımadan habersiz.
 */
import { api } from './client';
import { belirtecAl } from './oturum';
import type { components } from './schema';

export type KurulumDurumu = components['schemas']['DurumCiktisi'];
export type KurulumAdimi = components['schemas']['AdimCiktisi'];
export type MarkaGirdisi = components['schemas']['MarkaGirdisi'];
export type YuklemeRaporu = components['schemas']['YuklemeRaporu'];

export async function kurulumDurumu(): Promise<KurulumDurumu> {
  const { data, error } = await api.GET('/api/v1/setup');
  if (error) throw error;
  return data;
}

export async function markaKaydet(girdi: MarkaGirdisi): Promise<KurulumDurumu> {
  const { data, error } = await api.PUT('/api/v1/setup/brand', { body: girdi });
  if (error) throw error;
  return data;
}

export type KutuphaneSablonu = components['schemas']['KutuphaneSablonu'];
export type PlanOnerisi = components['schemas']['PlanOnerisi'];
export type YayinSonucu = components['schemas']['YayinSonucu'];

export async function kutuphane(): Promise<KutuphaneSablonu[]> {
  const { data, error } = await api.GET('/api/v1/setup/library');
  if (error) throw error;
  return data;
}

export async function sablonKopyala(key: string): Promise<{ version_id: string }> {
  const { data, error } = await api.POST('/api/v1/setup/template', { body: { key } });
  if (error) throw error;
  return data;
}

/**
 * Plan önerisi. Sürüm verilmezse sunucu **planı olmayan ilk yayınlanmış
 * sürümü** seçiyor: sihirbaz "hangi şablonu seçmiştim" diye durum
 * tutmuyor, tarayıcı kapanıp açılsa da aynı yeri gösteriyor (TC-004).
 */
export async function planOnerisi(): Promise<PlanOnerisi> {
  const { data, error } = await api.GET('/api/v1/setup/plan-proposal', {
    params: { query: {} },
  });
  if (error) throw error;
  return data;
}

export async function planOlustur(ad: string): Promise<KurulumDurumu> {
  const { data, error } = await api.POST('/api/v1/setup/plan', { body: { name: ad } });
  if (error) throw error;
  return data;
}

export async function kurulumYayinla(): Promise<YayinSonucu> {
  const { data, error } = await api.POST('/api/v1/setup/publish');
  if (error) throw error;
  return data;
}

export async function kurulumTamamla(): Promise<KurulumDurumu> {
  const { data, error } = await api.POST('/api/v1/setup/complete');
  if (error) throw error;
  return data;
}

async function dosyaIndir(yol: string, ad: string, govde?: FormData): Promise<void> {
  const yanit = await fetch(yol, {
    method: govde ? 'POST' : 'GET',
    headers: { Authorization: `Bearer ${belirtecAl() ?? ''}` },
    body: govde,
  });
  if (!yanit.ok) throw await yanit.json();
  // Tarayıcıya indirtmenin tek yolu bir bağlantıya tıklamak; nesne
  // URL'i hemen bırakılıyor, yoksa sekme kapanana kadar bellekte kalır.
  const url = URL.createObjectURL(await yanit.blob());
  const baglanti = document.createElement('a');
  baglanti.href = url;
  baglanti.download = ad;
  baglanti.click();
  URL.revokeObjectURL(url);
}

export function sablonIndir(): Promise<void> {
  return dosyaIndir('/api/v1/setup/branches/template', 'subeler.xlsx');
}

export function personelSablonuIndir(): Promise<void> {
  return dosyaIndir('/api/v1/setup/staff/template', 'personel.xlsx');
}

export function hataRaporuIndir(dosya: File, tur: Yukleme = 'branches'): Promise<void> {
  const govde = new FormData();
  govde.append('file', dosya);
  return dosyaIndir(`/api/v1/setup/${tur}/error-report`, 'hatali-satirlar.xlsx', govde);
}

/** Hangi liste yükleniyor: şubeler mi personel mi. */
export type Yukleme = 'branches' | 'staff';

async function dosyaGonder(
  dosya: File,
  tur: Yukleme,
  uc: 'preview' | 'import',
): Promise<YuklemeRaporu> {
  const govde = new FormData();
  govde.append('file', dosya);
  const yanit = await fetch(`/api/v1/setup/${tur}/${uc}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${belirtecAl() ?? ''}` },
    body: govde,
  });
  const icerik = await yanit.json();
  if (!yanit.ok) throw icerik;
  return icerik as YuklemeRaporu;
}

/** Kuru çalıştırma: ne olacağını yazmadan gösterir. */
export function subeOnizle(dosya: File): Promise<YuklemeRaporu> {
  return dosyaGonder(dosya, 'branches', 'preview');
}

export function subeYukle(dosya: File): Promise<YuklemeRaporu> {
  return dosyaGonder(dosya, 'branches', 'import');
}

export function personelOnizle(dosya: File): Promise<YuklemeRaporu> {
  return dosyaGonder(dosya, 'staff', 'preview');
}

export function personelYukle(dosya: File): Promise<YuklemeRaporu> {
  return dosyaGonder(dosya, 'staff', 'import');
}
