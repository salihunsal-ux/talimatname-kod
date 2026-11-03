import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { panoGetir, type Hucre } from '../../api/pano';
import { CalistirmaDetayi } from '../calistirma/CalistirmaDetayi';
import { tr } from '../../i18n/tr';
import { Dugme } from '../../bilesenler/Dugme';

/** Hücre görünümü: renk tek başına anlam taşımaz, ikon + başlık var (NFR-11). */
const HUCRE: Record<string, { ikon: string; zemin: string; yazi: string; ad: string }> = {
  submitted: {
    ikon: '✓',
    zemin: 'var(--renk-marka-acik)',
    yazi: 'var(--renk-marka)',
    ad: tr.plan.durumlar.submitted,
  },
  late: {
    ikon: '⏱',
    zemin: 'var(--renk-uyari-acik)',
    yazi: 'var(--renk-uyari)',
    ad: tr.pano.gecTamamlandi,
  },
  failed: {
    ikon: '!',
    zemin: 'var(--renk-kritik-acik)',
    yazi: 'var(--renk-kritik)',
    ad: tr.pano.basarisiz,
  },
  missed: {
    ikon: '✕',
    zemin: 'var(--renk-kritik-acik)',
    yazi: 'var(--renk-kritik)',
    ad: tr.plan.durumlar.missed,
  },
  in_progress: {
    ikon: '◐',
    zemin: 'var(--renk-uyari-acik)',
    yazi: 'var(--renk-uyari)',
    ad: tr.plan.durumlar.in_progress,
  },
  scheduled: {
    ikon: '○',
    zemin: 'var(--renk-yuzey2)',
    yazi: 'var(--renk-sessiz)',
    ad: tr.plan.durumlar.scheduled,
  },
  cancelled: {
    ikon: '–',
    zemin: 'var(--renk-yuzey2)',
    yazi: 'var(--renk-sessiz)',
    ad: tr.plan.durumlar.cancelled,
  },
  bos: { ikon: '', zemin: 'transparent', yazi: 'var(--renk-sessiz)', ad: tr.pano.kapsamDisi },
};

function hucreTuru(hucre: Hucre): keyof typeof HUCRE {
  if (!hucre.status) return 'bos';
  if (hucre.status === 'submitted') {
    if (hucre.result === 'failed') return 'failed';
    return hucre.late ? 'late' : 'submitted';
  }
  return hucre.status;
}

function bugunIso(): string {
  return new Date().toISOString().slice(0, 10);
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

  return (
    <div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--bosluk-3)',
          flexWrap: 'wrap',
          marginBottom: 'var(--bosluk-3)',
        }}
      >
        <h1 style={{ fontSize: 'var(--baslik-ekran)', margin: 0 }}>{tr.pano.baslik}</h1>
        <label style={{ display: 'flex', gap: 'var(--bosluk-2)', fontSize: 'var(--etiket)' }}>
          {tr.pano.isGunu}
          <input
            type="date"
            value={gun}
            onChange={(o) => setGun(o.target.value)}
            aria-label={tr.pano.isGunu}
            className="alan"
          />
        </label>
        {pano.isFetching && (
          <span style={{ color: 'var(--renk-sessiz)', fontSize: 'var(--meta)' }}>
            {tr.pano.yenileniyor}
          </span>
        )}
      </div>

      {pano.isError && (
        <p role="alert" style={{ color: 'var(--renk-kritik)' }}>
          {tr.hata.aglaBaglanilamadi}
        </p>
      )}

      {veri && <Gostergeler veri={veri} />}

      {veri && veri.rows.length === 0 && (
        <p style={{ color: 'var(--renk-sessiz)' }}>{tr.pano.gunBos}</p>
      )}

      {veri && veri.rows.length > 0 && veri.exception_row_count === 0 && !tumu && (
        <div
          role="status"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--bosluk-3)',
            background: veri.kpi.all_clear ? 'var(--renk-marka-acik)' : 'var(--renk-yuzey2)',
            color: 'var(--renk-murekkep)',
            borderRadius: 'var(--kose-kart)',
            padding: 'var(--bosluk-4)',
          }}
        >
          <span style={{ fontSize: 22 }} aria-hidden="true">
            {veri.kpi.all_clear ? '✓' : '○'}
          </span>
          <div>
            <strong>{veri.kpi.all_clear ? tr.pano.herSeyYolunda : tr.pano.henuzSorunYok}</strong>
            <div style={{ color: 'var(--renk-murekkep2)', fontSize: 'var(--etiket)' }}>
              {veri.kpi.all_clear
                ? tr.pano.herSeyYolundaAlt
                : `${veri.kpi.open_now} ${tr.pano.bekleyen}`}
            </div>
          </div>
        </div>
      )}

      {satirlar.length > 0 && veri && (
        <table className="tablo">
          <thead>
            <tr style={{ fontSize: 'var(--etiket)', color: 'var(--renk-sessiz)' }}>
              <th style={{ textAlign: 'left', padding: '4px 10px 4px 0' }}>{tr.pano.sube}</th>
              {veri.plans.map((plan) => (
                <th key={plan.id} style={{ textAlign: 'left', padding: '4px 10px' }}>
                  {plan.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {satirlar.map((satir) => (
              <tr key={satir.branch_id} style={{ borderTop: '1px solid var(--renk-cizgi)' }}>
                <th
                  scope="row"
                  style={{ textAlign: 'left', padding: '8px 10px 8px 0', fontWeight: 400 }}
                >
                  {satir.branch_name}
                  {satir.region_name && (
                    <span style={{ color: 'var(--renk-sessiz)', fontSize: 'var(--meta)' }}>
                      {' '}
                      · {satir.region_name}
                    </span>
                  )}
                </th>
                {satir.cells.map((hucre) => {
                  const tur = hucreTuru(hucre);
                  const g = HUCRE[tur];
                  return (
                    <td key={`${satir.branch_id}-${hucre.plan_id}`} style={{ padding: '6px 10px' }}>
                      <button
                        type="button"
                        disabled={!hucre.run_id}
                        onClick={() => hucre.run_id && setAcikCalistirma(hucre.run_id)}
                        title={`${g.ad}${
                          hucre.window_start
                            ? ` · ${pencere(veri.business_day, hucre.window_start, hucre.window_end)}`
                            : ''
                        }`}
                        className="izgara-hucre"
                        style={{ background: g.zemin, color: g.yazi }}
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
      )}

      {acikCalistirma && (
        <div style={{ marginTop: 'var(--bosluk-4)' }}>
          <CalistirmaDetayi runId={acikCalistirma} onKapat={() => setAcikCalistirma(null)} />
        </div>
      )}

      {veri && veri.rows.length > 0 && (
        <Dugme
          gorunum="ikincil"
          boyut="kucuk"
          type="button"
          onClick={() => setTumu(!tumu)}
          style={{ marginTop: 'var(--bosluk-3)' }}
        >
          {tumu
            ? tr.pano.yalnizcaSorunlu
            : `${tr.pano.tumunuGoster} (${veri.rows.length - veri.exception_row_count} ${tr.pano.sorunsuz})`}
        </Dugme>
      )}
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
