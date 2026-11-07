import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { panoGetir, type Hucre } from '../../api/pano';
import { CalistirmaDetayi } from '../calistirma/CalistirmaDetayi';
import { bugunIso } from '../../tarih';
import { tr } from '../../i18n/tr';
import { Hata } from '../../bilesenler/Durum';
import { IskeletOzet, IskeletTablo } from '../../bilesenler/Iskelet';
import { Dugme } from '../../bilesenler/Dugme';

/** Hücre görünümü: renk tek başına anlam taşımaz, ikon + başlık var (NFR-11). */
/**
 * Hücrenin durumu → ikon, renk sınıfı, ad. Renk çifti `.durum--*`
 * sınıflarında ve çiple ortak: palet iki yerde yazılıydı.
 */
const HUCRE: Record<string, { ikon: string; durum: string; ad: string }> = {
  submitted: { ikon: '✓', durum: 'marka', ad: tr.plan.durumlar.submitted },
  late: { ikon: '⏱', durum: 'uyari', ad: tr.pano.gecTamamlandi },
  failed: { ikon: '!', durum: 'kritik', ad: tr.pano.basarisiz },
  missed: { ikon: '✕', durum: 'kritik', ad: tr.plan.durumlar.missed },
  in_progress: { ikon: '◐', durum: 'uyari', ad: tr.plan.durumlar.in_progress },
  scheduled: { ikon: '○', durum: 'pasif', ad: tr.plan.durumlar.scheduled },
  cancelled: { ikon: '–', durum: 'pasif', ad: tr.plan.durumlar.cancelled },
  bos: { ikon: '', durum: 'bos', ad: tr.pano.kapsamDisi },
};

function hucreTuru(hucre: Hucre): keyof typeof HUCRE {
  if (!hucre.status) return 'bos';
  if (hucre.status === 'submitted') {
    if (hucre.result === 'failed') return 'failed';
    return hucre.late ? 'late' : 'submitted';
  }
  return hucre.status;
}

function saat(iso: string | null | undefined): string {
  return iso
    ? new Date(iso).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })
    : '';
}

function gun(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit' }) : '';
}

/**
 * Pencerenin okunabilir hâli. Gece yarısını aşan pencere (BR-01,
 * FR-0505) günsüz yazılınca yanıltıyor: "00:00–03:30", iş günü 2
 * Kasım olan satırda sabah geçmiş gibi okunuyor — oysa pencere o
 * gecenin sonunda açılıyor. PDF bunu iki tarihle yazıyordu; ızgara
 * yazmıyordu.
 */
function pencere(
  isGunu: string,
  bas: string | null | undefined,
  son: string | null | undefined,
): string {
  if (!bas) return '';
  const basGun = new Date(bas).toLocaleDateString('sv-SE'); // yerel YYYY-AA-GG
  const sonGun = son ? new Date(son).toLocaleDateString('sv-SE') : basGun;
  const onEk = basGun === isGunu ? '' : `${gun(bas)} `;
  const sonEk = sonGun === basGun ? '' : ` ${gun(son)}`;
  return `${onEk}${saat(bas)}–${saat(son)}${sonEk}`;
}

/**
 * SCR-W-07 · Operasyon panosu (E-4). **Varsayılan görünüm istisna
 * odaklıdır**: yalnızca sorunlu satırlar listelenir; sorun yoksa bunu
 * söyler. "Tümünü göster" ikinci istek atmaz — sunucu satırları
 * `exception` bayrağıyla gönderiyor (FR-1219).
 *
 * 60 saniyede bir kendiliğinden tazelenir (ST-077).
 */
export function PanoSayfasi() {
  const [gun, setGun] = useState(bugunIso());
  const [tumu, setTumu] = useState(false);
  const [acikCalistirma, setAcikCalistirma] = useState<string | null>(null);

  const pano = useQuery({
    queryKey: ['pano', gun],
    queryFn: () => panoGetir(gun),
    refetchInterval: 60_000,
  });

  const veri = pano.data;
  const satirlar = veri ? (tumu ? veri.rows : veri.rows.filter((r) => r.exception)) : [];

  const satirSayisi = veri ? veri.rows.length : 0;

  return (
    <div>
      <header className="sayfa-basligi">
        <div>
          <h1>{tr.pano.baslik}</h1>
          <p className="sayfa-basligi-alt">
            {tr.pano.altBaslik}
            {pano.isFetching && <span className="durum-metni"> · {tr.pano.yenileniyor}</span>}
          </p>
        </div>

        <div className="sayfa-basligi-denetimler">
          {veri && satirSayisi > 0 && (
            <Dugme
              gorunum="ikincil"
              boyut="kucuk"
              type="button"
              aria-pressed={tumu}
              onClick={() => setTumu(!tumu)}
            >
              {tumu
                ? tr.pano.yalnizcaSorunlu
                : `${tr.pano.tumunuGoster} (${veri.rows.length - veri.exception_row_count} ${tr.pano.sorunsuz})`}
            </Dugme>
          )}
          <label className="sayfa-basligi-denetim">
            <span className="alan-etiket">{tr.pano.isGunu}</span>
            <input
              type="date"
              value={gun}
              onChange={(o) => setGun(o.target.value)}
              aria-label={tr.pano.isGunu}
              className="alan"
            />
          </label>
        </div>
      </header>

      <div className="yigin">
        {pano.isError && <Hata hata={pano.error} metin={tr.hata.aglaBaglanilamadi} />}

        {/* Panonun hiç yükleme hâli yoktu: veri gelene kadar sayfa
            başlıktan ibaret kalıyordu. En çok beklenen ekran bu. */}
        {pano.isPending && (
          <>
            <IskeletOzet />
            <IskeletTablo sutunlar={3} satirlar={5} />
          </>
        )}

        {veri && <Gostergeler veri={veri} />}

        {veri && veri.rows.length === 0 && <p className="bos-durum">{tr.pano.gunBos}</p>}

        {veri && veri.rows.length > 0 && veri.exception_row_count === 0 && !tumu && (
          <div role="status" className={veri.kpi.all_clear ? 'mujde mujde--temiz' : 'mujde'}>
            <span className="mujde-ikon" aria-hidden="true">
              {veri.kpi.all_clear ? '✓' : '○'}
            </span>
            <div>
              <strong>{veri.kpi.all_clear ? tr.pano.herSeyYolunda : tr.pano.henuzSorunYok}</strong>
              <div className="ikincil-metin">
                {veri.kpi.all_clear
                  ? tr.pano.herSeyYolundaAlt
                  : `${veri.kpi.open_now} ${tr.pano.bekleyen}`}
              </div>
            </div>
          </div>
        )}

        {satirlar.length > 0 && veri && (
          <div className="tablo-kaydirma">
            <table className="tablo tablo--izgara">
              <thead>
                <tr>
                  <th>{tr.pano.sube}</th>
                  {veri.plans.map((plan) => (
                    <th key={plan.id}>{plan.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {satirlar.map((satir) => (
                  <tr key={satir.branch_id}>
                    <th scope="row">
                      {satir.branch_name}
                      {satir.region_name && <span className="meta"> · {satir.region_name}</span>}
                    </th>
                    {satir.cells.map((hucre) => {
                      const tur = hucreTuru(hucre);
                      const g = HUCRE[tur];
                      return (
                        <td key={`${satir.branch_id}-${hucre.plan_id}`}>
                          {/* Seçili hâlin tek kaynağı `aria-pressed`:
                            satır vurgusu da bundan türüyor. */}
                          <button
                            type="button"
                            disabled={!hucre.run_id}
                            onClick={() => hucre.run_id && setAcikCalistirma(hucre.run_id)}
                            aria-pressed={
                              hucre.run_id ? acikCalistirma === hucre.run_id : undefined
                            }
                            title={`${g.ad}${
                              hucre.window_start
                                ? ` · ${pencere(veri.business_day, hucre.window_start, hucre.window_end)}`
                                : ''
                            }`}
                            className={`izgara-hucre durum--${g.durum}`}
                          >
                            <span aria-hidden="true">{g.ikon}</span>
                            {g.ad}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Detay yuvası boş bırakılmıyor: ızgaranın altındaki boşluk
          "sayfa bitti" gibi okunuyordu, oysa asıl içerik bir tık
          uzakta. */}
        {acikCalistirma ? (
          <CalistirmaDetayi runId={acikCalistirma} onKapat={() => setAcikCalistirma(null)} />
        ) : (
          satirlar.length > 0 && <p className="bos-durum">{tr.pano.detayIpucu}</p>
        )}
      </div>
    </div>
  );
}

function Gostergeler({
  veri,
}: {
  veri: {
    kpi: {
      total: number;
      submitted: number;
      late: number;
      missed: number;
      open_now: number;
      completion_percent: number | null;
    };
  };
}) {
  const { kpi } = veri;
  return (
    <div className="ozet-serit">
      <div className="ozet-manset">
        <span className="ozet-manset-ad">{tr.pano.tamamlanma}</span>
        <span className="ozet-manset-deger">
          {kpi.completion_percent === null ? '—' : `%${kpi.completion_percent}`}
        </span>
      </div>

      <div className="ozet-kutular">
        <Gosterge ad={tr.pano.calistirma} deger={String(kpi.total)} />
        <Gosterge ad={tr.plan.durumlar.submitted} deger={String(kpi.submitted)} />
        <Gosterge
          ad={tr.pano.gec}
          deger={String(kpi.late)}
          vurgu={kpi.late > 0 ? 'uyari' : undefined}
        />
        <Gosterge
          ad={tr.plan.durumlar.missed}
          deger={String(kpi.missed)}
          vurgu={kpi.missed > 0 ? 'kritik' : undefined}
        />
        <Gosterge ad={tr.pano.bekleyenKisa} deger={String(kpi.open_now)} />
      </div>
    </div>
  );
}

function Gosterge({ ad, deger, vurgu }: { ad: string; deger: string; vurgu?: 'uyari' | 'kritik' }) {
  return (
    <div className={vurgu ? `ozet-kutu ozet-kutu--${vurgu}` : 'ozet-kutu'}>
      <div className="ozet-kutu-ad">{ad}</div>
      <div className="ozet-kutu-deger">{deger}</div>
    </div>
  );
}
