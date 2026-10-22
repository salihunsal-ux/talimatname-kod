import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { panoGetir, type Hucre } from '../../api/pano';
import { tr } from '../../i18n/tr';

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
        <h1 style={{ fontSize: 'var(--baslik-bolum)', margin: 0 }}>{tr.pano.baslik}</h1>
        <label style={{ display: 'flex', gap: 'var(--bosluk-2)', fontSize: 'var(--etiket)' }}>
          {tr.pano.isGunu}
          <input
            type="date"
            value={gun}
            onChange={(o) => setGun(o.target.value)}
            aria-label={tr.pano.isGunu}
            style={alan}
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
        <table style={{ borderCollapse: 'collapse', marginTop: 'var(--bosluk-3)' }}>
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
                      <span
                        title={`${g.ad}${hucre.window_start ? ` · ${saat(hucre.window_start)}–${saat(hucre.window_end)}` : ''}`}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 6,
                          minWidth: 112,
                          minHeight: 32,
                          padding: '0 var(--bosluk-3)',
                          borderRadius: 'var(--kose-dugme)',
                          background: g.zemin,
                          color: g.yazi,
                          fontSize: 'var(--etiket)',
                          fontWeight: 600,
                        }}
                      >
                        <span aria-hidden="true">{g.ikon}</span>
                        {g.ad}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {veri && veri.rows.length > 0 && (
        <button
          type="button"
          onClick={() => setTumu(!tumu)}
          style={{
            marginTop: 'var(--bosluk-3)',
            padding: '0 var(--bosluk-3)',
            minHeight: 36,
            borderRadius: 'var(--kose-dugme)',
            border: '1px solid var(--renk-cizgi)',
            background: 'var(--renk-yuzey2)',
            color: 'var(--renk-murekkep)',
            cursor: 'pointer',
            fontSize: 'var(--etiket)',
          }}
        >
          {tumu
            ? tr.pano.yalnizcaSorunlu
            : `${tr.pano.tumunuGoster} (${veri.rows.length - veri.exception_row_count} ${tr.pano.sorunsuz})`}
        </button>
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
    <div
      style={{
        display: 'flex',
        gap: 'var(--bosluk-3)',
        flexWrap: 'wrap',
        marginBottom: 'var(--bosluk-4)',
      }}
    >
      <Gosterge
        ad={tr.pano.tamamlanma}
        deger={kpi.completion_percent === null ? '—' : `%${kpi.completion_percent}`}
      />
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
  );
}

function Gosterge({ ad, deger, vurgu }: { ad: string; deger: string; vurgu?: 'uyari' | 'kritik' }) {
  return (
    <div
      style={{
        minWidth: 110,
        padding: 'var(--bosluk-3)',
        borderRadius: 'var(--kose-kart)',
        border: '1px solid var(--renk-cizgi)',
        background: 'var(--renk-yuzey)',
      }}
    >
      <div style={{ fontSize: 'var(--meta)', color: 'var(--renk-sessiz)' }}>{ad}</div>
      <div
        style={{
          fontSize: 28,
          fontWeight: 700,
          fontVariantNumeric: 'tabular-nums',
          color: vurgu ? `var(--renk-${vurgu})` : 'var(--renk-murekkep)',
        }}
      >
        {deger}
      </div>
    </div>
  );
}

const alan = {
  height: 36,
  padding: '0 var(--bosluk-2)',
  borderRadius: 'var(--kose-dugme)',
  border: '1px solid var(--renk-cizgi)',
  background: 'var(--renk-yuzey)',
  color: 'var(--renk-murekkep)',
} as const;
