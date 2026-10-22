/** Şablon veri erişimi (ST-016, ST-017). */
import { api } from './client';
import type { components } from './schema';

export type SablonOzet = components['schemas']['SablonOzet'];
export type SurumDetay = components['schemas']['SurumDetay'];
export type SurumOzet = components['schemas']['SurumOzet'];
export type MaddeGirdisi = components['schemas']['MaddeGirdisi'];
export type BolumGirdisi = components['schemas']['BolumGirdisi'];
export type TaslakGirdisi = components['schemas']['TaslakGirdisi'];
export type MaddeTuru = MaddeGirdisi['type'];

export async function sablonListesi(): Promise<SablonOzet[]> {
  const { data, error } = await api.GET('/api/v1/templates');
  if (error) throw error;
  return data;
}

export async function surumDetayi(id: string): Promise<SurumDetay> {
  const { data, error } = await api.GET('/api/v1/template-versions/{version_id}', {
    params: { path: { version_id: id } },
  });
  if (error) throw error;
  return data;
}

export async function sablonOlustur(name: string): Promise<SurumDetay> {
  const { data, error } = await api.POST('/api/v1/templates', { body: { name } });
  if (error) throw error;
  return data;
}

export async function taslakKaydet(id: string, girdi: TaslakGirdisi): Promise<SurumDetay> {
  const { data, error } = await api.PUT('/api/v1/template-versions/{version_id}', {
    params: { path: { version_id: id } },
    body: girdi,
  });
  if (error) throw error;
  return data;
}

export async function yeniTaslak(templateId: string): Promise<SurumDetay> {
  const { data, error } = await api.POST('/api/v1/templates/{template_id}/new-draft', {
    params: { path: { template_id: templateId } },
  });
  if (error) throw error;
  return data;
}

export async function surumYayinla(id: string): Promise<SurumDetay> {
  const { data, error } = await api.POST('/api/v1/template-versions/{version_id}/publish', {
    params: { path: { version_id: id } },
  });
  if (error) throw error;
  return data;
}
