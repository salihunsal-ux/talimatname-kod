/**
 * Oturum: belirtecin saklanması ve kimlik uç noktaları (ST-004, ST-005).
 *
 * Belirteç `localStorage`'ta tutuluyor: sekme kapanınca oturum düşmesin.
 * Bu, XSS karşısında httpOnly çerez kadar güvenli değil — v1'de panel
 * tek kaynaktan servis edileceği ve CSP kurulacağı için kabul edildi;
 * kalıcı oturum için yenileme belirteci ST-044'te ele alınacak.
 */
import { api } from './client';
import type { components } from './schema';

export type Ben = components['schemas']['BenYaniti'];
export type KodYaniti = components['schemas']['KodYaniti'];
export type Oturum = components['schemas']['OturumYaniti'];

const ANAHTAR = 'talimatname.belirtec';

let bellekteki: string | null = null;

/** Depodan okur; özel pencerede erişim hata verebilir, sessizce geçeriz. */
function depodanOku(): string | null {
  try {
    return localStorage.getItem(ANAHTAR);
  } catch {
    return null;
  }
}

export function belirtecAl(): string | null {
  if (bellekteki === null) bellekteki = depodanOku();
  return bellekteki;
}

export function belirtecYaz(yeni: string | null): void {
  bellekteki = yeni;
  try {
    if (yeni === null) localStorage.removeItem(ANAHTAR);
    else localStorage.setItem(ANAHTAR, yeni);
  } catch {
    /* depo kapalıysa oturum yalnızca bu sayfa ömrü boyunca sürer */
  }
}

/** Her isteğe belirteci ekler. Tek yer: çağrı noktaları başlık bilmez. */
api.use({
  onRequest({ request }) {
    const belirtec = belirtecAl();
    if (belirtec !== null) request.headers.set('Authorization', `Bearer ${belirtec}`);
    return request;
  },
});

export async function kodIste(telefon: string): Promise<KodYaniti> {
  const { data, error } = await api.POST('/api/v1/auth/request-code', {
    body: { phone: telefon },
  });
  if (error) throw error;
  return data;
}

export async function kodDogrula(telefon: string, kod: string): Promise<Oturum> {
  const { data, error } = await api.POST('/api/v1/auth/verify', {
    body: { phone: telefon, code: kod },
  });
  if (error) throw error;
  belirtecYaz(data.access_token);
  return data;
}

export async function benGetir(): Promise<Ben> {
  const { data, error } = await api.GET('/api/v1/auth/me');
  if (error) throw error;
  return data;
}

export function cikisYap(): void {
  belirtecYaz(null);
}
