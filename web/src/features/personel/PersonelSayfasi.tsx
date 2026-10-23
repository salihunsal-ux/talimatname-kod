import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { problemCoz } from '../../api/client';
import {
  personelDavet,
  personelMaskele,
  personelPasiflestir,
  personelListesi,
  type KullaniciOzet,
  type Rol,
} from '../../api/personel';
import { subeAgaci } from '../../api/subeler';
import { Cip } from '../../bilesenler/Cip';
import { useYonetici } from '../../api/yetki';
import { tr } from '../../i18n/tr';

const ROLLER: { deger: Rol; etiket: string; kapsam: 'yok' | 'bolge' | 'sube' }[] = [
  { deger: 'admin', etiket: 'Yönetici', kapsam: 'yok' },
  { deger: 'region_manager', etiket: 'Bölge müdürü', kapsam: 'bolge' },
  { deger: 'branch_manager', etiket: 'Şube müdürü', kapsam: 'sube' },
  { deger: 'staff', etiket: 'Personel', kapsam: 'sube' },
];

/**
 * SCR-W-03 · Personel ve roller: liste, süzme, davet, pasifleştirme ve
 * KVKK maskelemesi. Rolün kapsamı rolden belirlenir; arayüz yalnızca
 * gereken seçiciyi gösterir (FR-0205).
 */
export function PersonelSayfasi() {
  const yonetici = useYonetici();
  const [subeSuzgeci, setSubeSuzgeci] = useState<string>('');
  const [rolSuzgeci, setRolSuzgeci] = useState<string>('');
  const [pasifDahil, setPasifDahil] = useState(false);

  const subeler = useQuery({
    queryKey: ['subeler', { pasifDahil: false }],
    queryFn: () => subeAgaci(),
  });
  const personel = useQuery({
    queryKey: ['personel', { subeSuzgeci, rolSuzgeci, pasifDahil }],
    queryFn: () =>
      personelListesi({
        branchId: subeSuzgeci || undefined,
        role: (rolSuzgeci as Rol) || undefined,
        includeInactive: pasifDahil,
      }),
  });

  const duzSubeler = (subeler.data ?? []).flatMap((bolge) =>
    bolge.branches.map((sube) => ({ ...sube, bolge: bolge.name })),
  );
  // Kapsam adı hem şube hem bölge olabilir: ikisini tek haritada topluyoruz.
  const kapsamAdlari = new Map<string, string>();
  for (const bolge of subeler.data ?? []) {
    if (bolge.id) kapsamAdlari.set(bolge.id, bolge.name);
    for (const sube of bolge.branches) kapsamAdlari.set(sube.id, sube.name);
  }

  return (
    <div>
      <h1 style={{ fontSize: 'var(--baslik-bolum)', margin: '0 0 var(--bosluk-3)' }}>
        {tr.personel.baslik}
      </h1>

      <div
        style={{
          display: 'flex',
          gap: 'var(--bosluk-3)',
          flexWrap: 'wrap',
          alignItems: 'center',
          marginBottom: 'var(--bosluk-4)',
        }}
      >
        <label style={etiketBicimi}>
          {tr.personel.sube}
          <select
            value={subeSuzgeci}
            onChange={(o) => setSubeSuzgeci(o.target.value)}
            style={secimBicimi}
          >
            <option value="">{tr.personel.hepsi}</option>
            {duzSubeler.map((sube) => (
              <option key={sube.id} value={sube.id}>
                {sube.name} ({sube.code})
              </option>
            ))}
          </select>
        </label>

        <label style={etiketBicimi}>
          {tr.personel.rol}
          <select
            value={rolSuzgeci}
            onChange={(o) => setRolSuzgeci(o.target.value)}
            style={secimBicimi}
          >
            <option value="">{tr.personel.hepsi}</option>
            {ROLLER.map((rol) => (
              <option key={rol.deger} value={rol.deger}>
                {rol.etiket}
              </option>
            ))}
          </select>
        </label>

        <label style={{ display: 'flex', gap: 'var(--bosluk-2)', fontSize: 'var(--etiket)' }}>
          <input
            type="checkbox"
            checked={pasifDahil}
            onChange={(o) => setPasifDahil(o.target.checked)}
          />
          {tr.personel.pasifleriGoster}
        </label>
      </div>

      {personel.isPending && <p style={{ color: 'var(--renk-sessiz)' }}>{tr.genel.yukleniyor}</p>}
      {personel.isError && (
        <p role="alert" style={{ color: 'var(--renk-kritik)' }}>
          {tr.hata.aglaBaglanilamadi}
        </p>
      )}

      {personel.data && personel.data.length === 0 && (
        <p style={{ color: 'var(--renk-sessiz)' }}>{tr.personel.bos}</p>
      )}

      {personel.data && personel.data.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--govde)' }}>
          <thead>
            <tr
              style={{ textAlign: 'left', color: 'var(--renk-sessiz)', fontSize: 'var(--etiket)' }}
            >
              <th style={{ padding: '6px 0' }}>{tr.personel.ad}</th>
              <th>{tr.personel.rolKapsam}</th>
              <th>{tr.personel.telefon}</th>
              <th style={{ textAlign: 'right' }}>{tr.personel.islem}</th>
            </tr>
          </thead>
          <tbody>
            {personel.data.map((kisi) => (
              <PersonelSatiri key={kisi.id} kisi={kisi} kapsamAdi={kapsamAdiCozucu(kapsamAdlari)} />
            ))}
          </tbody>
        </table>
      )}

      {yonetici && <DavetFormu subeler={duzSubeler} />}
    </div>
  );
}

function PersonelSatiri({
  kisi,
  kapsamAdi,
}: {
  kisi: KullaniciOzet;
  kapsamAdi: (id: string | null | undefined) => string;
}) {
  const kuyruk = useQueryClient();
  const [maskeOnayi, setMaskeOnayi] = useState(false);

  const tazele = async () => {
    await kuyruk.invalidateQueries({ queryKey: ['personel'] });
  };
  const pasiflestir = useMutation({
    mutationFn: () => personelPasiflestir(kisi.id),
    onSuccess: tazele,
  });
  const maskele = useMutation({ mutationFn: () => personelMaskele(kisi.id), onSuccess: tazele });

  return (
    <tr style={{ borderTop: '1px solid var(--renk-cizgi)' }}>
      <td style={{ padding: '10px 0' }}>
        {kisi.full_name}
        {kisi.status === 'inactive' && (
          <>
            {' '}
            <Cip renk="pasif" ikon="–" metin={tr.personel.pasif} />
          </>
        )}
        {kisi.status === 'masked' && (
          <>
            {' '}
            <Cip renk="pasif" ikon="•" metin={tr.personel.maskeli} />
          </>
        )}
      </td>
      <td>
        {kisi.assignments.length === 0 ? (
          <span style={{ color: 'var(--renk-sessiz)' }}>—</span>
        ) : (
          kisi.assignments.map((atama, sira) => (
            <div key={`${atama.role}-${sira}`} style={{ fontSize: 'var(--etiket)' }}>
              {atama.role_label}
              {atama.scope_type !== 'tenant' && (
                <span style={{ color: 'var(--renk-sessiz)' }}> · {kapsamAdi(atama.scope_id)}</span>
              )}
            </div>
          ))
        )}
      </td>
      <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--renk-murekkep2)' }}>
        {kisi.phone ?? '—'}
      </td>
      <td style={{ textAlign: 'right' }}>
        {kisi.status === 'active' && (
          <button type="button" onClick={() => pasiflestir.mutate()} style={kucukDugme}>
            {tr.personel.pasiflestir}
          </button>
        )}
        {kisi.status !== 'masked' &&
          (maskeOnayi ? (
            <button
              type="button"
              onClick={() => maskele.mutate()}
              style={{ ...kucukDugme, color: 'var(--renk-kritik)' }}
            >
              {tr.personel.maskeleOnay}
            </button>
          ) : (
            <button type="button" onClick={() => setMaskeOnayi(true)} style={kucukDugme}>
              {tr.personel.maskele}
            </button>
          ))}
      </td>
    </tr>
  );
}

function DavetFormu({ subeler }: { subeler: { id: string; name: string; code: string }[] }) {
  const kuyruk = useQueryClient();
  const [ad, setAd] = useState('');
  const [telefon, setTelefon] = useState('');
  const [rol, setRol] = useState<Rol>('staff');
  const [kapsam, setKapsam] = useState('');

  const secili = ROLLER.find((r) => r.deger === rol);
  const kapsamGerekli = secili?.kapsam !== 'yok';

  const davet = useMutation({
    mutationFn: () =>
      personelDavet({
        full_name: ad,
        phone: telefon,
        assignments: [{ role: rol, scope_id: kapsamGerekli ? kapsam : null }],
      }),
    onSuccess: async () => {
      setAd('');
      setTelefon('');
      setKapsam('');
      await kuyruk.invalidateQueries({ queryKey: ['personel'] });
    },
  });

  const problem = problemCoz(davet.error);

  return (
    <form
      onSubmit={(olay) => {
        olay.preventDefault();
        davet.mutate();
      }}
      style={{
        display: 'flex',
        gap: 'var(--bosluk-2)',
        flexWrap: 'wrap',
        alignItems: 'flex-end',
        marginTop: 'var(--bosluk-6)',
        paddingTop: 'var(--bosluk-4)',
        borderTop: '1px solid var(--renk-cizgi)',
      }}
    >
      <label style={etiketBicimi}>
        {tr.personel.ad}
        <input
          value={ad}
          onChange={(o) => setAd(o.target.value)}
          required
          style={girdiBicimi(170)}
        />
      </label>
      <label style={etiketBicimi}>
        {tr.personel.telefon}
        <input
          value={telefon}
          onChange={(o) => setTelefon(o.target.value)}
          required
          placeholder="0532 123 45 67"
          style={girdiBicimi(150)}
        />
      </label>
      <label style={etiketBicimi}>
        {tr.personel.rol}
        <select value={rol} onChange={(o) => setRol(o.target.value as Rol)} style={secimBicimi}>
          {ROLLER.map((r) => (
            <option key={r.deger} value={r.deger}>
              {r.etiket}
            </option>
          ))}
        </select>
      </label>
      {kapsamGerekli && (
        <label style={etiketBicimi}>
          {secili?.kapsam === 'bolge' ? tr.personel.bolge : tr.personel.sube}
          <select
            value={kapsam}
            onChange={(o) => setKapsam(o.target.value)}
            required
            style={secimBicimi}
          >
            <option value="">{tr.personel.seciniz}</option>
            {subeler.map((sube) => (
              <option key={sube.id} value={sube.id}>
                {sube.name} ({sube.code})
              </option>
            ))}
          </select>
        </label>
      )}
      <button
        type="submit"
        disabled={davet.isPending}
        style={{
          padding: '0 var(--bosluk-4)',
          borderRadius: 'var(--kose-dugme)',
          border: '1px solid var(--renk-marka)',
          background: 'var(--renk-marka)',
          color: '#fff',
          cursor: 'pointer',
        }}
      >
        {tr.personel.davet}
      </button>

      {davet.isError && (
        <p role="alert" style={{ width: '100%', margin: 0, color: 'var(--renk-kritik)' }}>
          {problem ? problem.title : tr.hata.genel}
          {problem?.errors?.length ? `: ${problem.errors[0].sebep}` : ''}
        </p>
      )}
      {davet.isSuccess && (
        <p role="status" style={{ width: '100%', margin: 0, color: 'var(--renk-murekkep2)' }}>
          {tr.personel.davetKuyrukta}
        </p>
      )}
    </form>
  );
}

function kapsamAdiCozucu(adlar: Map<string, string>) {
  return (id: string | null | undefined) =>
    id ? (adlar.get(id) ?? tr.personel.bilinmeyenKapsam) : '';
}

const etiketBicimi = {
  display: 'grid',
  gap: 'var(--bosluk-1)',
  fontSize: 'var(--etiket)',
} as const;

const secimBicimi = {
  height: 36,
  padding: '0 var(--bosluk-2)',
  borderRadius: 'var(--kose-dugme)',
  border: '1px solid var(--renk-cizgi)',
  background: 'var(--renk-yuzey)',
  color: 'var(--renk-murekkep)',
} as const;

const kucukDugme = {
  padding: '0 var(--bosluk-3)',
  marginLeft: 'var(--bosluk-2)',
  minHeight: 32,
  borderRadius: 'var(--kose-dugme)',
  border: '1px solid var(--renk-cizgi)',
  background: 'var(--renk-yuzey2)',
  color: 'var(--renk-murekkep)',
  cursor: 'pointer',
  fontSize: 'var(--etiket)',
} as const;

function girdiBicimi(genislik: number) {
  return { ...secimBicimi, width: genislik } as const;
}
