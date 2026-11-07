/**
 * Oturum: belirtecin saklanması ve kimlik uç noktaları (ST-004, ST-005).
 *
 * Belirteç `localStorage`'ta tutuluyor: sekme kapanınca oturum düşmesin.
 * Bu, XSS karşısında httpOnly çerez kadar güvenli değil — v1'de panel
 * tek kaynaktan servis edileceği ve CSP kurulacağı için kabul edildi.
 *
 * İki belirteç var (FR-0203): kısa ömürlü **erişim** belirteci her
 * isteğe takılıyor, uzun ömürlü **yenileme** belirteci yalnızca
 * `/auth/refresh`e gidiyor. Erişim belirtecinin süresi dolmadan
 * sessizce yenileniyor; kullanıcı bunu görmüyor. Önceden tek belirteç
 * vardı ve 30 dakikada bir, panelin ortasında giriş ekranına
 * düşülüyordu.
 */
import { api } from './client';
import type { components } from './schema';

export type Ben = components['schemas']['BenYaniti'];
export type KodYaniti = components['schemas']['KodYaniti'];
export type Oturum = components['schemas']['OturumYaniti'];

const ANAHTAR = 'talimatname.belirtec';
const YENILEME_ANAHTARI = 'talimatname.yenileme';
const SONERME_ANAHTARI = 'talimatname.sonerme';

/**
 * Erişim belirteci bu kadar kalınca yenileniyor. Bir isteğin gidip
 * dönmesi ile saat kayması için pay: sunucuya "az önce doldu" diyen
 * bir belirteçle gitmeyelim.
 */
const YENILEME_PAYI_MS = 60_000;

let bellekteki: string | null = null;

/** Depodan okur; özel pencerede erişim hata verebilir, sessizce geçeriz. */
function depodanOku(anahtar: string): string | null {
  try {
    return localStorage.getItem(anahtar);
  } catch {
    return null;
  }
}

function depoyaYaz(anahtar: string, deger: string | null): void {
  try {
    if (deger === null) localStorage.removeItem(anahtar);
    else localStorage.setItem(anahtar, deger);
  } catch {
    /* depo kapalıysa oturum yalnızca bu sayfa ömrü boyunca sürer */
  }
}

export function belirtecAl(): string | null {
  if (bellekteki === null) bellekteki = depodanOku(ANAHTAR);
  return bellekteki;
}

export function belirtecYaz(yeni: string | null): void {
  bellekteki = yeni;
  depoyaYaz(ANAHTAR, yeni);
}

export function yenilemeBelirteciAl(): string | null {
  return depodanOku(YENILEME_ANAHTARI);
}

/** Oturumun üç parçasını birlikte yazar: ikisi ayrı düşmesin. */
function oturumuSakla(oturum: Oturum): void {
  belirtecYaz(oturum.access_token);
  depoyaYaz(YENILEME_ANAHTARI, oturum.refresh_token);
  depoyaYaz(SONERME_ANAHTARI, String(Date.now() + oturum.expires_in_minutes * 60_000));
}

function oturumuSil(): void {
  belirtecYaz(null);
  depoyaYaz(YENILEME_ANAHTARI, null);
  depoyaYaz(SONERME_ANAHTARI, null);
}

function sonermeYakin(): boolean {
  const ham = depodanOku(SONERME_ANAHTARI);
  if (ham === null) return false;
  const sonerme = Number(ham);
  if (!Number.isFinite(sonerme)) return true;
  return Date.now() + YENILEME_PAYI_MS >= sonerme;
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

/**
 * Kendi kimliğini **gövdede** taşıyan uçlar: giriş, yenileme, çıkış.
 *
 * İkisini birden yapıyorlar — erişim belirteci takılmıyor ve yenileme
 * tetiklenmiyor. Tetiklenseydi `/auth/refresh` kendi kendini çağırırdı;
 * başlık eklenseydi süresi dolmuş bir belirteç, ihtiyaç duymayan bir uca
 * boşuna gönderilirdi (`/verify/` için de aynı gerekçe geçerli).
 */
const KIMLIK_YOLLARI = [
  '/api/v1/auth/request-code',
  '/api/v1/auth/verify',
  '/api/v1/auth/refresh',
  '/api/v1/auth/logout',
];

/** Aynı anda tek yenileme: beş sorgu birden dönünce beş istek gitmesin. */
let yenilemeIsi: Promise<boolean> | null = null;

/**
 * Erişim belirtecini sessizce tazeler. Dönen: başarılı mı.
 *
 * Başarısızlıkta oturum düşürülüyor — yenileme belirteci de
 * geçersizse yapacak bir şey kalmıyor ve kullanıcıyı 403 duvarına
 * koşturmaktansa giriş ekranına almak dürüst.
 */
export async function tazele(): Promise<boolean> {
  const yenileme = yenilemeBelirteciAl();
  if (yenileme === null) return false;
  yenilemeIsi ??= (async () => {
    try {
      const { data, error } = await api.POST('/api/v1/auth/refresh', {
        body: { refresh_token: yenileme },
      });
      if (error || !data) {
        oturumDustu();
        return false;
      }
      oturumuSakla(data);
      return true;
    } finally {
      yenilemeIsi = null;
    }
  })();
  return yenilemeIsi;
}

/** Her isteğe belirteci ekler. Tek yer: çağrı noktaları başlık bilmez. */
api.use({
  async onRequest({ request }) {
    const kimliksiz = [...OTURUMSUZ_YOLLAR, ...KIMLIK_YOLLARI].some((yol) =>
      request.url.includes(yol),
    );
    if (kimliksiz) return request;
    if (sonermeYakin()) await tazele();
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
  oturumuSakla(data);
  return data;
}

export async function benGetir(): Promise<Ben> {
  const { data, error } = await api.GET('/api/v1/auth/me');
  if (error) throw error;
  return data;
}

/**
 * Çıkış: yenileme belirtecini **sunucuda da** iptal eder.
 *
 * Yalnızca yerelden silmek yetmezdi; belirteç kopyalanmış olabilir ve
 * 12 saat daha geçerli kalırdı. Sunucuya ulaşılamazsa yerel silme yine
 * yapılıyor: kullanıcı çıkmak istediğini söyledi.
 */
export async function cikisYap(): Promise<void> {
  const yenileme = yenilemeBelirteciAl();
  if (yenileme !== null) {
    try {
      await api.POST('/api/v1/auth/logout', { body: { refresh_token: yenileme } });
    } catch {
      /* ağ yoksa yerel silme yeter; belirteç süresi dolunca düşer */
    }
  }
  oturumuSil();
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
  oturumuSil();
  for (const dinleyici of dinleyiciler) dinleyici();
}
