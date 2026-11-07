/**
 * Saha istemcisi veri erişimi (ST-030, ST-033).
 *
 * Mobilin bağlanacağı yüzeyin **aynısı**: cevap kimliği burada
 * üretiliyor ve yolda gidiyor (`PUT .../answers/{answer_id}`), kanıt
 * üç adımda yükleniyor (izin → bayt → tamamla). Fark, çevrimdışı
 * kuyruk yok: bu istemci yalnızca çevrimiçi çalışır ve Spike A'nın
 * yerine geçmez.
 */
import { api } from './client';
import type { components } from './schema';

export type CevapGirdisi = components['schemas']['CevapGirdisi'];
export type CevapCiktisi = components['schemas']['CevapCiktisi'];
export type SurumDetay = components['schemas']['SurumDetay'];
export type ManifestCiktisi = components['schemas']['ManifestCiktisi'];

const CIHAZ_ANAHTARI = 'talimatname.cihaz';

/**
 * Cihaz kimliği: tarayıcı başına bir UUID. Sunucu bunu cevabın ve
 * kanıtın yanına yazıyor; "hangi cihazdan geldi" sorusu kâğıtta da
 * sorulabilsin. Depolama kapalıysa her oturum yeni kimlik üretir —
 * kayıt yine yazılır, yalnızca cihaz takibi kopar.
 */
export function cihazKimligi(): string {
  try {
    const mevcut = localStorage.getItem(CIHAZ_ANAHTARI);
    if (mevcut !== null) return mevcut;
    const yeni = crypto.randomUUID();
    localStorage.setItem(CIHAZ_ANAHTARI, yeni);
    return yeni;
  } catch {
    return crypto.randomUUID();
  }
}

export async function senkManifesti(): Promise<ManifestCiktisi> {
  const { data, error } = await api.GET('/api/v1/sync/manifest', {
    params: { header: { 'X-Device-Time': new Date().toISOString() } },
  });
  if (error) throw error;
  return data;
}

export async function surumDetayi(versionId: string): Promise<SurumDetay> {
  const { data, error } = await api.GET('/api/v1/template-versions/{version_id}', {
    params: { path: { version_id: versionId } },
  });
  if (error) throw error;
  return data;
}

export async function cevapYaz(
  runId: string,
  answerId: string,
  girdi: CevapGirdisi,
): Promise<CevapCiktisi> {
  const { data, error } = await api.PUT('/api/v1/runs/{run_id}/answers/{answer_id}', {
    params: { path: { run_id: runId, answer_id: answerId } },
    body: { ...girdi, device_id: cihazKimligi(), device_reported_at: new Date().toISOString() },
  });
  if (error) throw error;
  return data;
}

export async function listeyiGonder(runId: string): Promise<unknown> {
  const { data, error } = await api.POST('/api/v1/runs/{run_id}/submit', {
    params: { path: { run_id: runId } },
    body: {},
  });
  if (error) throw error;
  return data;
}

/** Tarayıcıda SHA-256: sunucu baytları alınca aynısını hesaplayıp karşılaştırıyor. */
async function ozet(bayt: ArrayBuffer): Promise<string> {
  const ham = await crypto.subtle.digest('SHA-256', bayt);
  return [...new Uint8Array(ham)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/** Sunucunun kabul ettiği kanıt türleri (`ALLOWED_TYPES`). */
export type KanitTuru = 'image/jpeg' | 'image/png';

/**
 * Dosyanın gönderilecek tür etiketi.
 *
 * Eskiden PNG dışındaki **her** dosya `image/jpeg` diye etiketleniyor
 * ama baytları dönüştürülmüyordu: dosya seçici `image/*` kabul ettiği
 * için WebP/HEIC/GIF yanlış etiketle depoya gidiyordu (bağımsız test
 * turu B12). Özeti baytlardan hesaplandığı için yükleme geçiyor, ama
 * depodaki kayıt yalan söylüyor ve önizleme bozulabiliyordu.
 *
 * Dönüştürmek yerine **reddediyoruz**: tarayıcıda yeniden kodlamak
 * kanıtın baytlarını değiştirir, damgalanan şey artık çekilen dosya
 * olmaz.
 */
export function kanitTuru(dosya: File): KanitTuru {
  const tur = dosya.type.toLowerCase();
  if (tur === 'image/png') return 'image/png';
  if (tur === 'image/jpeg' || tur === 'image/jpg') return 'image/jpeg';
  throw new DesteklenmeyenTur(dosya.type || 'bilinmeyen');
}

/** Kanıt olarak yüklenemeyen dosya türü. */
export class DesteklenmeyenTur extends Error {
  readonly tur: string;

  constructor(tur: string) {
    super(`Desteklenmeyen dosya türü: ${tur}`);
    this.name = 'DesteklenmeyenTur';
    this.tur = tur;
  }
}

/**
 * Kanıt yükleme: izin → bayt → tamamla (FR-0606).
 *
 * `from_gallery` **her zaman true**: tarayıcı "yalnızca kamera"yı
 * garanti edemiyor, `capture` bir ipucu. Sunucu bu bayrağı kanıdın
 * yanına yazıyor, panelde ⚑ olarak görünüyor. Demo yalan söylemiyor;
 * bayrak doğruyu söylüyor.
 */
export async function kanitYukle(
  runId: string,
  answerId: string,
  itemId: string,
  dosya: File,
): Promise<void> {
  const bayt = await dosya.arrayBuffer();
  const tur = kanitTuru(dosya);

  const { data: izin, error: izinHatasi } = await api.POST(
    '/api/v1/runs/{run_id}/answers/{answer_id}/evidence',
    {
      params: { path: { run_id: runId, answer_id: answerId } },
      body: {
        item_id: itemId,
        sha256: await ozet(bayt),
        content_type: tur,
        size_bytes: dosya.size,
        from_gallery: true,
        captured_at: new Date(dosya.lastModified).toISOString(),
        device_id: cihazKimligi(),
        device_reported_at: new Date().toISOString(),
      },
    },
  );
  if (izinHatasi) throw izinHatasi;

  // Bayt yüklemesi üretilmiş istemciden geçmiyor: gövde JSON değil ham
  // dosya ve uç nokta oturum istemiyor, yetki belirteç yolunda.
  const yanit = await fetch(izin.upload_url, {
    method: izin.upload_method ?? 'PUT',
    headers: { 'content-type': tur },
    body: bayt,
  });
  if (!yanit.ok) throw new Error(`Yükleme başarısız: ${yanit.status}`);

  const { error: tamamHatasi } = await api.POST('/api/v1/evidence/{evidence_id}/complete', {
    params: { path: { evidence_id: izin.evidence.id } },
  });
  if (tamamHatasi) throw tamamHatasi;
}
