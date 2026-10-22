import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { problemCoz } from '../../api/client';
import { subeAgaci, subeDetayi, subeEkle, subePasiflestir } from '../../api/subeler';
import { tr } from '../../i18n/tr';
import { Cip } from '../../bilesenler/Cip';

/**
 * SCR-W-02 · Şubeler: solda bölge → şube ağacı, sağda şube detayı.
 * Veri bugün bellek içi tohumdan geliyor; veritabanı bağlanınca (ücretsiz
 * bulut PostgreSQL) bu ekran değişmez — aynı uç noktalar.
 */
export function SubelerSayfasi() {
  const [secili, setSecili] = useState<string | null>(null);
  const [pasifDahil, setPasifDahil] = useState(false);

  const agac = useQuery({
    queryKey: ['subeler', { pasifDahil }],
    queryFn: () => subeAgaci(pasifDahil),
  });

  return (
    <div style={{ display: 'flex', gap: 'var(--bosluk-6)', flexWrap: 'wrap' }}>
      <div style={{ flex: '1 1 320px', minWidth: 280 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 'var(--bosluk-3)',
            marginBottom: 'var(--bosluk-3)',
          }}
        >
          <h1 style={{ fontSize: 'var(--baslik-bolum)', margin: 0 }}>{tr.subeler.baslik}</h1>
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--bosluk-2)',
              fontSize: 'var(--etiket)',
            }}
          >
            <input
              type="checkbox"
              checked={pasifDahil}
              onChange={(olay) => setPasifDahil(olay.target.checked)}
            />
            {tr.subeler.pasifleriGoster}
          </label>
        </div>

        {agac.isPending && <p style={{ color: 'var(--renk-sessiz)' }}>{tr.genel.yukleniyor}</p>}
        {agac.isError && (
          <p role="alert" style={{ color: 'var(--renk-kritik)' }}>
            {tr.hata.aglaBaglanilamadi}
          </p>
        )}

        {agac.data?.map((bolge) => (
          <section key={bolge.id ?? 'bolgesiz'} style={{ marginBottom: 'var(--bosluk-4)' }}>
            <h2
              style={{
                fontSize: 'var(--etiket)',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: 'var(--renk-sessiz)',
                margin: '0 0 var(--bosluk-2)',
              }}
            >
              {bolge.name} · {bolge.branches.length}
            </h2>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {bolge.branches.map((sube) => (
                <li key={sube.id}>
                  <button
                    type="button"
                    onClick={() => setSecili(sube.id)}
                    aria-current={secili === sube.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 'var(--bosluk-3)',
                      width: '100%',
                      padding: 'var(--bosluk-2) var(--bosluk-3)',
                      marginBottom: 'var(--bosluk-1)',
                      textAlign: 'left',
                      borderRadius: 'var(--kose-dugme)',
                      border: '1px solid',
                      borderColor: secili === sube.id ? 'var(--renk-marka)' : 'var(--renk-cizgi)',
                      background:
                        secili === sube.id ? 'var(--renk-marka-acik)' : 'var(--renk-yuzey)',
                      color: 'var(--renk-murekkep)',
                      cursor: 'pointer',
                    }}
                  >
                    <code
                      style={{
                        fontSize: 'var(--meta)',
                        color: 'var(--renk-sessiz)',
                        minWidth: 42,
                      }}
                    >
                      {sube.code}
                    </code>
                    <span style={{ flex: 1 }}>{sube.name}</span>
                    {sube.status === 'inactive' ? (
                      <Cip renk="pasif" ikon="–" metin={tr.subeler.pasif} />
                    ) : (
                      <span style={{ fontSize: 'var(--meta)', color: 'var(--renk-sessiz)' }}>
                        {sube.open_days} {tr.subeler.gunKisaltma}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}

        <SubeEkleFormu />
      </div>

      <div style={{ flex: '1 1 360px', minWidth: 300 }}>
        {secili ? (
          <SubeDetayi id={secili} onPasiflestirildi={() => setSecili(null)} />
        ) : (
          <p style={{ color: 'var(--renk-sessiz)' }}>{tr.subeler.secimYok}</p>
        )}
      </div>
    </div>
  );
}

function SubeDetayi({ id, onPasiflestirildi }: { id: string; onPasiflestirildi: () => void }) {
  const kuyruk = useQueryClient();
  const detay = useQuery({ queryKey: ['sube', id], queryFn: () => subeDetayi(id) });
  const pasiflestir = useMutation({
    mutationFn: () => subePasiflestir(id),
    onSuccess: async () => {
      await kuyruk.invalidateQueries({ queryKey: ['subeler'] });
      await kuyruk.invalidateQueries({ queryKey: ['sube', id] });
      onPasiflestirildi();
    },
  });

  if (detay.isPending) return <p style={{ color: 'var(--renk-sessiz)' }}>{tr.genel.yukleniyor}</p>;
  if (detay.isError || !detay.data)
    return (
      <p role="alert" style={{ color: 'var(--renk-kritik)' }}>
        {tr.hata.genel}
      </p>
    );

  const sube = detay.data;

  return (
    <article
      style={{
        background: 'var(--renk-yuzey)',
        border: '1px solid var(--renk-cizgi)',
        borderRadius: 'var(--kose-kart)',
        padding: 'var(--bosluk-4)',
      }}
    >
      <header style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--bosluk-3)' }}>
        <h2 style={{ fontSize: 'var(--baslik-bolum)', margin: 0 }}>{sube.name}</h2>
        <code style={{ color: 'var(--renk-sessiz)' }}>{sube.code}</code>
        {sube.status === 'inactive' && <Cip renk="pasif" ikon="–" metin={tr.subeler.pasif} />}
      </header>
      {sube.address && (
        <p style={{ color: 'var(--renk-murekkep2)', margin: 'var(--bosluk-2) 0 0' }}>
          {sube.address}
        </p>
      )}

      <h3 style={{ fontSize: 'var(--etiket)', marginTop: 'var(--bosluk-4)' }}>
        {tr.subeler.calismaSaatleri}
      </h3>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--etiket)' }}>
        <tbody>
          {sube.business_hours.map((gun) => (
            <tr key={gun.weekday} style={{ borderTop: '1px solid var(--renk-cizgi)' }}>
              <th scope="row" style={{ textAlign: 'left', fontWeight: 400, padding: '6px 0' }}>
                {gun.weekday_name}
              </th>
              <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                {gun.open_time ? (
                  `${saat(gun.open_time)} – ${saat(gun.close_time)}`
                ) : (
                  <span style={{ color: 'var(--renk-sessiz)' }}>{tr.subeler.kapali}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={{ fontSize: 'var(--etiket)', marginTop: 'var(--bosluk-4)' }}>
        {tr.subeler.istasyonlar}
      </h3>
      <ul
        style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--bosluk-2)', padding: 0, margin: 0 }}
      >
        {sube.stations.map((istasyon) => (
          <li key={istasyon.id} style={{ listStyle: 'none' }}>
            <Cip renk="nötr" metin={istasyon.name} />
          </li>
        ))}
      </ul>

      {sube.status === 'active' && (
        <button
          type="button"
          onClick={() => pasiflestir.mutate()}
          disabled={pasiflestir.isPending}
          style={{
            marginTop: 'var(--bosluk-4)',
            padding: '0 var(--bosluk-4)',
            borderRadius: 'var(--kose-dugme)',
            border: '1px solid var(--renk-cizgi)',
            background: 'var(--renk-yuzey2)',
            color: 'var(--renk-kritik)',
            cursor: 'pointer',
          }}
        >
          {tr.subeler.pasiflestir}
        </button>
      )}
      <p style={{ fontSize: 'var(--meta)', color: 'var(--renk-sessiz)' }}>
        {tr.subeler.pasiflestirmeNotu}
      </p>
    </article>
  );
}

function SubeEkleFormu() {
  const kuyruk = useQueryClient();
  const [kod, setKod] = useState('');
  const [ad, setAd] = useState('');
  const ekle = useMutation({
    // Saat dilimi şimdilik sabit: hesap varsayılanı modellenince (CAP-01)
    // forma seçici gelecek; zincirlerin çoğu tek saat diliminde.
    mutationFn: () => subeEkle({ code: kod, name: ad, timezone: 'Europe/Istanbul' }),
    onSuccess: async () => {
      setKod('');
      setAd('');
      await kuyruk.invalidateQueries({ queryKey: ['subeler'] });
    },
  });

  const problem = problemCoz(ekle.error);

  return (
    <form
      onSubmit={(olay) => {
        olay.preventDefault();
        ekle.mutate();
      }}
      style={{
        display: 'flex',
        gap: 'var(--bosluk-2)',
        flexWrap: 'wrap',
        alignItems: 'flex-end',
        marginTop: 'var(--bosluk-4)',
        paddingTop: 'var(--bosluk-4)',
        borderTop: '1px solid var(--renk-cizgi)',
      }}
    >
      <label style={{ display: 'grid', gap: 'var(--bosluk-1)', fontSize: 'var(--etiket)' }}>
        {tr.subeler.kod}
        <input
          value={kod}
          onChange={(olay) => setKod(olay.target.value)}
          required
          maxLength={16}
          style={girdiBicimi(72)}
        />
      </label>
      <label style={{ display: 'grid', gap: 'var(--bosluk-1)', fontSize: 'var(--etiket)' }}>
        {tr.subeler.ad}
        <input
          value={ad}
          onChange={(olay) => setAd(olay.target.value)}
          required
          maxLength={80}
          style={girdiBicimi(180)}
        />
      </label>
      <button
        type="submit"
        disabled={ekle.isPending}
        style={{
          padding: '0 var(--bosluk-4)',
          borderRadius: 'var(--kose-dugme)',
          border: '1px solid var(--renk-marka)',
          background: 'var(--renk-marka)',
          color: '#fff',
          cursor: 'pointer',
        }}
      >
        {tr.subeler.ekle}
      </button>
      {ekle.isError && (
        <p role="alert" style={{ width: '100%', margin: 0, color: 'var(--renk-kritik)' }}>
          {problem ? problem.title : tr.hata.genel}
          {problem?.errors?.length ? `: ${problem.errors[0].sebep}` : ''}
        </p>
      )}
    </form>
  );
}

function girdiBicimi(genislik: number) {
  return {
    width: genislik,
    height: 36,
    padding: '0 var(--bosluk-2)',
    borderRadius: 'var(--kose-dugme)',
    border: '1px solid var(--renk-cizgi)',
    background: 'var(--renk-yuzey)',
    color: 'var(--renk-murekkep)',
  } as const;
}

/** "08:00:00" → "08:00" */
function saat(deger: string | null | undefined): string {
  return deger ? deger.slice(0, 5) : '';
}
