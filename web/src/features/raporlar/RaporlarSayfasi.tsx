import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { kanitBaglantisi } from '../../api/kanitlar';
import {
  aylikOzet,
  kanitGalerisi,
  olcumGunlugu,
  type AylikOzet,
  type GaleriKanidi,
  type OlcumSerisi,
} from '../../api/raporlar';
import { Cip } from '../../bilesenler/Cip';
import { tr } from '../../i18n/tr';

type Sekme = 'ozet' | 'olcum' | 'galeri';

/**
 * SCR-W-09 · Raporlar (ST-090): aylık özet (FR-1220), ölçüm günlüğü
 * (FR-1207) ve kanıt galerisi (FR-1208).
 *
 * Üçü de denetim konuşmasının parçası — bu yüzden aynı sayfada:
 * "ay nasıl geçti", "sıcaklıklar ne durumda", "kanıtı göster".
 */
export function RaporlarSayfasi() {
  const [sekme, setSekme] = useState<Sekme>('ozet');
  const bugun = new Date();
  const [yil, setYil] = useState(bugun.getFullYear());
  const [ay, setAy] = useState(bugun.getMonth() + 1);

  return (
    <div>
      <h1 style={{ fontSize: 'var(--baslik-bolum)', margin: 0 }}>{tr.rapor.baslik}</h1>

      <div
        role="tablist"
        aria-label={tr.rapor.baslik}
        style={{ display: 'flex', gap: 'var(--bosluk-2)', margin: 'var(--bosluk-4) 0' }}
      >
        {(
          [
            ['ozet', tr.rapor.aylikOzet],
            ['olcum', tr.rapor.olcumGunlugu],
            ['galeri', tr.rapor.galeri],
          ] as const
        ).map(([anahtar, ad]) => (
          <button
            key={anahtar}
            role="tab"
            aria-selected={sekme === anahtar}
            onClick={() => setSekme(anahtar)}
            style={{
              minHeight: 44,
              padding: '0 var(--bosluk-4)',
              borderRadius: 'var(--kose-dugme)',
              border: `1px solid ${sekme === anahtar ? 'var(--renk-marka)' : 'var(--renk-cizgi)'}`,
              background: sekme === anahtar ? 'var(--renk-marka-acik)' : 'var(--renk-yuzey2)',
              color: 'var(--renk-murekkep)',
              cursor: 'pointer',
            }}
          >
            {ad}
          </button>
        ))}
      </div>

      {sekme === 'ozet' && <AylikOzetBolumu yil={yil} ay={ay} onYil={setYil} onAy={setAy} />}
      {sekme === 'olcum' && <OlcumBolumu />}
      {sekme === 'galeri' && <GaleriBolumu />}
    </div>
  );
}

function aralik(gunSayisi: number): { ilk: string; son: string } {
  const son = new Date();
  const ilk = new Date(son.getTime() - gunSayisi * 24 * 60 * 60 * 1000);
  return { ilk: ilk.toISOString().slice(0, 10), son: son.toISOString().slice(0, 10) };
}

function AylikOzetBolumu({
  yil,
  ay,
  onYil,
  onAy,
}: {
  yil: number;
  ay: number;
  onYil: (y: number) => void;
  onAy: (a: number) => void;
}) {
  const ozet = useQuery({ queryKey: ['rapor-aylik', yil, ay], queryFn: () => aylikOzet(yil, ay) });

  return (
    <section>
      <div style={{ display: 'flex', gap: 'var(--bosluk-3)', alignItems: 'end', flexWrap: 'wrap' }}>
        <label style={etiket}>
          {tr.rapor.ay}
          <select value={ay} onChange={(o) => onAy(Number(o.target.value))} style={alan}>
            {tr.rapor.aylar.map((ad, sira) => (
              <option key={ad} value={sira + 1}>
                {ad}
              </option>
            ))}
          </select>
        </label>
        <label style={etiket}>
          {tr.rapor.yil}
          <input
            type="number"
            value={yil}
            min={2020}
            max={2100}
            onChange={(o) => onYil(Number(o.target.value))}
            style={{ ...alan, width: 120 }}
          />
        </label>
      </div>

      {ozet.isPending && <p style={{ color: 'var(--renk-sessiz)' }}>{tr.genel.yukleniyor}</p>}
      {ozet.isError && (
        <p role="alert" style={{ color: 'var(--renk-kritik)' }}>
          {tr.hata.aglaBaglanilamadi}
        </p>
      )}
      {ozet.data && <OzetKartlari ozet={ozet.data} />}
      {ozet.data && ozet.data.branches.length > 0 && <SubeTablosu ozet={ozet.data} />}
      {ozet.data && ozet.data.counters.total === 0 && (
        <p style={{ color: 'var(--renk-sessiz)' }}>{tr.rapor.kayitYok}</p>
      )}
    </section>
  );
}

function OzetKartlari({ ozet }: { ozet: AylikOzet }) {
  const s = ozet.counters;
  // Anahtar etiketten değil alandan: iki kart aynı sözcükle
  // başlayabiliyor ("Zamanında tamamlanma" ve "Zamanında").
  const kartlar: [string, string, string][] = [
    ['yuzde', tr.rapor.zamanindaYuzde, s.on_time_percent === null ? '—' : `%${s.on_time_percent}`],
    ['toplam', tr.rapor.toplam, String(s.total)],
    ['zamaninda', tr.rapor.zamaninda, String(s.on_time)],
    ['gec', tr.rapor.gec, String(s.late)],
    ['kacirilan', tr.rapor.kacirilan, String(s.missed)],
    ['basarisiz', tr.rapor.basarisiz, String(s.failed)],
    ['yapilamadi', tr.rapor.yapilamadi, String(s.not_done_items)],
    ['acik', tr.rapor.acik, String(s.open)],
  ];

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
        gap: 'var(--bosluk-3)',
        margin: 'var(--bosluk-4) 0',
      }}
    >
      {kartlar.map(([anahtar, ad, deger]) => (
        <div
          key={anahtar}
          style={{
            border: '1px solid var(--renk-cizgi)',
            borderRadius: 'var(--kose-kart)',
            padding: 'var(--bosluk-3)',
            background: 'var(--renk-yuzey)',
          }}
        >
          <div style={{ fontSize: 'var(--etiket)', color: 'var(--renk-murekkep2)' }}>{ad}</div>
          <div style={{ fontSize: 'var(--baslik-kart)', marginTop: 4 }}>{deger}</div>
        </div>
      ))}
    </div>
  );
}

function SubeTablosu({ ozet }: { ozet: AylikOzet }) {
  return (
    <>
      <h2 style={{ fontSize: 'var(--baslik-kart)' }}>{tr.rapor.subeKirilimi}</h2>
      <p style={{ color: 'var(--renk-murekkep2)', fontSize: 'var(--etiket)' }}>
        {tr.rapor.siraAciklamasi}
      </p>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={baslikHucre}>{tr.rapor.sube}</th>
            <th style={baslikHucre}>{tr.rapor.zamanindaYuzde}</th>
            <th style={baslikHucre}>{tr.rapor.zamaninda}</th>
            <th style={baslikHucre}>{tr.rapor.gec}</th>
            <th style={baslikHucre}>{tr.rapor.kacirilan}</th>
            <th style={baslikHucre}>{tr.rapor.basarisiz}</th>
          </tr>
        </thead>
        <tbody>
          {ozet.branches.map((sube) => (
            <tr key={sube.branch_id}>
              <td style={hucre}>
                {sube.branch_name}{' '}
                <span style={{ color: 'var(--renk-sessiz)' }}>{sube.branch_code}</span>
              </td>
              <td style={hucre}>
                {sube.counters.on_time_percent === null ? (
                  <span style={{ color: 'var(--renk-sessiz)' }}>{tr.rapor.olculemedi}</span>
                ) : (
                  `%${sube.counters.on_time_percent}`
                )}
              </td>
              <td style={hucre}>{sube.counters.on_time}</td>
              <td style={hucre}>{sube.counters.late}</td>
              <td style={hucre}>{sube.counters.missed}</td>
              <td style={hucre}>{sube.counters.failed}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function OlcumBolumu() {
  const [yalnizAralikDisi, setYalnizAralikDisi] = useState(false);
  const { ilk, son } = aralik(30);
  const seriler = useQuery({
    queryKey: ['rapor-olcum', ilk, son, yalnizAralikDisi],
    queryFn: () => olcumGunlugu(ilk, son, yalnizAralikDisi),
  });

  return (
    <section>
      <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--bosluk-2)' }}>
        <input
          type="checkbox"
          checked={yalnizAralikDisi}
          onChange={(o) => setYalnizAralikDisi(o.target.checked)}
        />
        {tr.rapor.yalnizAralikDisi}
      </label>
      <p style={{ color: 'var(--renk-murekkep2)', fontSize: 'var(--etiket)' }}>
        {tr.rapor.olcumAciklamasi}
      </p>

      {seriler.isPending && <p style={{ color: 'var(--renk-sessiz)' }}>{tr.genel.yukleniyor}</p>}
      {seriler.data?.length === 0 && (
        <p style={{ color: 'var(--renk-sessiz)' }}>{tr.rapor.olcumYok}</p>
      )}
      {(seriler.data ?? []).map((seri) => (
        <OlcumSerisiKarti key={seri.item_id} seri={seri} />
      ))}
    </section>
  );
}

function OlcumSerisiKarti({ seri }: { seri: OlcumSerisi }) {
  const aralikMetni =
    seri.min_value !== null && seri.max_value !== null
      ? `${seri.min_value}–${seri.max_value}${seri.unit ?? ''}`
      : '—';

  return (
    <div
      style={{
        border: '1px solid var(--renk-cizgi)',
        borderRadius: 'var(--kose-kart)',
        padding: 'var(--bosluk-4)',
        marginBottom: 'var(--bosluk-3)',
        background: 'var(--renk-yuzey)',
      }}
    >
      <div
        style={{ display: 'flex', gap: 'var(--bosluk-2)', alignItems: 'center', flexWrap: 'wrap' }}
      >
        <strong>{seri.item_title}</strong>
        <Cip renk="nötr" metin={tr.rapor.kabulAraligi.replace('{a}', aralikMetni)} />
        {seri.out_of_range_count > 0 ? (
          <Cip
            renk="kritik"
            ikon="!"
            metin={tr.rapor.aralikDisiSayisi.replace('{n}', String(seri.out_of_range_count))}
          />
        ) : (
          <Cip renk="marka" ikon="✓" metin={tr.rapor.hepsiAralikta} />
        )}
      </div>

      <ul style={{ listStyle: 'none', padding: 0, margin: 'var(--bosluk-3) 0 0' }}>
        {seri.points.slice(-12).map((nokta, sira) => (
          <li
            key={`${nokta.run_id}-${sira}`}
            style={{
              display: 'flex',
              gap: 'var(--bosluk-3)',
              padding: '2px 0',
              color: nokta.out_of_range ? 'var(--renk-kritik)' : undefined,
            }}
          >
            <span style={{ minWidth: 150, color: 'var(--renk-murekkep2)' }}>
              {nokta.measured_at ? new Date(nokta.measured_at).toLocaleString('tr-TR') : '—'}
            </span>
            <span>
              {nokta.value}
              {seri.unit ?? ''}
            </span>
            {nokta.out_of_range && <span>{tr.rapor.aralikDisi}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function GaleriBolumu() {
  const [yalnizBayrakli, setYalnizBayrakli] = useState(false);
  const { ilk, son } = aralik(14);
  const kanitlar = useQuery({
    queryKey: ['rapor-galeri', ilk, son, yalnizBayrakli],
    queryFn: () => kanitGalerisi(ilk, son, yalnizBayrakli),
  });

  return (
    <section>
      <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--bosluk-2)' }}>
        <input
          type="checkbox"
          checked={yalnizBayrakli}
          onChange={(o) => setYalnizBayrakli(o.target.checked)}
        />
        {tr.rapor.yalnizBayrakli}
      </label>

      {kanitlar.isPending && <p style={{ color: 'var(--renk-sessiz)' }}>{tr.genel.yukleniyor}</p>}
      {kanitlar.data?.length === 0 && (
        <p style={{ color: 'var(--renk-sessiz)' }}>{tr.rapor.kanitYok}</p>
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
          gap: 'var(--bosluk-3)',
          marginTop: 'var(--bosluk-4)',
        }}
      >
        {(kanitlar.data ?? []).map((kanit) => (
          <GaleriKarti key={kanit.id} kanit={kanit} />
        ))}
      </div>
    </section>
  );
}

function GaleriKarti({ kanit }: { kanit: GaleriKanidi }) {
  // Çalıştırma detayındaki ile aynı kural: açılamayan görsel kırık
  // simge değil, ne olduğunu söyleyen bir kutu olmalı.
  const [acilmadi, setAcilmadi] = useState(false);
  const baglanti = useQuery({
    queryKey: ['kanit-baglanti', kanit.id, 'thumbnail'],
    queryFn: () => kanitBaglantisi(kanit.id, 'thumbnail'),
    staleTime: 10 * 60 * 1000,
  });

  return (
    <figure style={{ margin: 0 }}>
      {baglanti.data && !acilmadi ? (
        <img
          src={baglanti.data}
          alt={tr.kanit.gorselAlt}
          onError={() => setAcilmadi(true)}
          style={{
            width: '100%',
            height: 120,
            objectFit: 'cover',
            borderRadius: 'var(--kose-kart)',
            border: '1px solid var(--renk-cizgi)',
          }}
        />
      ) : (
        <div
          style={{
            height: 120,
            display: 'grid',
            placeItems: 'center',
            borderRadius: 'var(--kose-kart)',
            border: '1px solid var(--renk-cizgi)',
            background: 'var(--renk-yuzey2)',
            color: 'var(--renk-sessiz)',
            fontSize: 'var(--etiket)',
          }}
        >
          {baglanti.isError || acilmadi ? tr.kanit.acilamadi : tr.genel.yukleniyor}
        </div>
      )}
      <figcaption style={{ fontSize: 'var(--etiket)', color: 'var(--renk-murekkep2)' }}>
        {new Date(kanit.captured_at ?? kanit.created_at).toLocaleString('tr-TR')}
        {kanit.flags && kanit.flags.length > 0 && (
          <span style={{ display: 'block', color: 'var(--renk-uyari)' }}>
            ⚑ {kanit.flags.join(' · ')}
          </span>
        )}
      </figcaption>
    </figure>
  );
}

const etiket = {
  display: 'block',
  fontSize: 'var(--etiket)',
  color: 'var(--renk-murekkep2)',
} as const;

const alan = {
  display: 'block',
  minHeight: 44,
  marginTop: 'var(--bosluk-2)',
  padding: '0 var(--bosluk-3)',
  borderRadius: 'var(--kose-dugme)',
  border: '1px solid var(--renk-cizgi)',
  background: 'var(--renk-yuzey2)',
  color: 'var(--renk-murekkep)',
  fontSize: 'var(--govde)',
} as const;

const baslikHucre = {
  textAlign: 'left',
  fontSize: 'var(--etiket)',
  color: 'var(--renk-murekkep2)',
  borderBottom: '1px solid var(--renk-cizgi)',
  padding: 'var(--bosluk-2)',
} as const;

const hucre = {
  borderBottom: '1px solid var(--renk-cizgi)',
  padding: 'var(--bosluk-2)',
} as const;
