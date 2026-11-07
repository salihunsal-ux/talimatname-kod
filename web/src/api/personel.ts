/** Personel veri erişimi (ST-013). Tipler OpenAPI'den üretilir. */
import { api } from './client';
import type { components } from './schema';

export type KullaniciOzet = components['schemas']['KullaniciOzet'];
export type KullaniciGirdisi = components['schemas']['KullaniciGirdisi'];
export type DavetYaniti = components['schemas']['DavetYaniti'];
export type KullaniciDuzeltmesi = components['schemas']['KullaniciDuzeltmeGirdisi'];
/** Rol birleşimi şemada ayrı ad taşımıyor; atama gövdesinden türetiyoruz. */
export type Rol = components['schemas']['RolGirdisi']['role'];

export async function personelListesi(secenek: {
  branchId?: string;
  role?: Rol;
  includeInactive?: boolean;
}): Promise<KullaniciOzet[]> {
  const { data, error } = await api.GET('/api/v1/users', {
    params: {
      query: {
        branch_id: secenek.branchId,
        role: secenek.role,
        include_inactive: secenek.includeInactive ?? false,
      },
    },
  });
  if (error) throw error;
  return data;
}

export async function personelDavet(girdi: KullaniciGirdisi): Promise<DavetYaniti> {
  const { data, error } = await api.POST('/api/v1/users', { body: girdi });
  if (error) throw error;
  return data;
}

export async function personelPasiflestir(id: string): Promise<KullaniciOzet> {
  const { data, error } = await api.POST('/api/v1/users/{user_id}/deactivate', {
    params: { path: { user_id: id } },
  });
  if (error) throw error;
  return data;
}

export async function personelMaskele(id: string): Promise<KullaniciOzet> {
  const { data, error } = await api.POST('/api/v1/users/{user_id}/mask', {
    params: { path: { user_id: id } },
  });
  if (error) throw error;
  return data;
}

/**
 * Ad ya da e-posta düzeltmesi. Telefon bu uçtan değişmez: numara
 * kişinin kimliği (giriş ve içe aktarma anahtarı).
 */
export async function personelDuzelt(
  id: string,
  degisiklik: KullaniciDuzeltmesi,
): Promise<KullaniciOzet> {
  const { data, error } = await api.PATCH('/api/v1/users/{user_id}', {
    params: { path: { user_id: id } },
    body: degisiklik,
  });
  if (error) throw error;
  return data;
}
