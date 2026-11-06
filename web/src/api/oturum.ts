/**
 * Oturum: belirtecin saklanması ve kimlik uç noktaları (ST-004, ST-005).
 *
 * Belirteç `localStorage`'ta tutuluyor: sekme kapanınca oturum düşmesin.
 * Bu, XSS karşısında httpOnly çerez kadar güvenli değil — v1'de panel
 * tek kaynaktan servis edileceği ve CSP kurulacağı için kabul edildi;
 * kalıcı oturum için yenileme belirteci henüz **hiçbir hikâyede
 * yok** (bu satır ST-044'ü gösteriyordu, o bildirim servisi).
 * FR-0203 web oturumunu 12 saat ve iptal edilebilir yenileme
 * belirteciyle istiyor; açık iş ürün dosyasında:
 * 04-gereksinimler/08-oturum-suresi-acigi.md.
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

/**
 * Oturum **istemeyen** yollar: belge doğrulama (FR-1218).
 *
 * Açık bir sayfa kimlik bilgisi taşımamalı. Tarayıcıda eski bir
 * belirteç kalmış olabilir (müdürün tabletinde denetçi doğrulama
 * yapıyor olabilir) ve o belirteci dışarıya açık bir uç noktaya
 * göndermenin hiçbir faydası yok.
 */
const OTURUMSUZ_YOLLAR = ['/api/v1/verify/'];

/** Her isteğe belirteci ekler. Tek yer: çağrı noktaları başlık bilmez. */
api.use({
  onRequest({ request }) {
    if (OTURUMSUZ_YOLLAR.some((yol) => request.url.includes(yol))) return request;
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

/**
 * Oturum düşüşü: belirteç 30 dakika yaşıyor ve yenileme belirteci yok
 * (ST-044). Süre dolduğunda kullanıcı panelin ortasında kalıyordu —
 * her istek 403 veriyor ama ekran duruyordu. Artık sunucu oturumu
 * reddettiği anda belirteç bırakılıyor ve uygulama giriş ekranına
 * dönüyor.
 *
 * Abonelik React'in dışında: hatayı sorgu önbelleği yakalıyor, ekranı
 * ise `App` değiştiriyor.
 */
type OturumDinleyici = () => void;
const dinleyiciler = new Set<OturumDinleyici>();

export function oturumDinle(dinleyici: OturumDinleyici): () => void {
  dinleyiciler.add(dinleyici);
  return () => dinleyiciler.delete(dinleyici);
}

export function oturumDustu(): void {
  // Zaten düşmüşse ikinci kez duyurma: aynı turda birkaç sorgu
  // birden 403 alıyor ve her biri burayı çağırıyor.
  if (belirtecAl() === null) return;
  belirtecYaz(null);
  for (const dinleyici of dinleyiciler) dinleyici();
}
