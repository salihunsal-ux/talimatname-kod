import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { problemCoz } from '../../api/client';
import {
  aksiyonAc,
  aksiyonKapat,
  aksiyonListesi,
  aksiyonSayaclari,
  type AksiyonOzet,
  type Oncelik,
} from '../../api/aksiyonlar';
import { subeAgaci } from '../../api/subeler';
import { Cip } from '../../bilesenler/Cip';
import { tr } from '../../i18n/tr';

const ONCELIKLER: { deger: Oncelik; etiket: string; renk: 'kritik' | 'uyari' | 'nötr' }[] = [
  { deger: 'critical', etiket: 'Kritik', renk: 'kritik' },
  { deger: 'high', etiket: 'Yüksek', renk: 'uyari' },
  { deger: 'normal', etiket: 'Normal', renk: 'nötr' },
];

function vadeMetni(aksiyon: AksiyonOzet): string {
  if (aksiyon.status === 'closed') return '';
  const kalan = aksiyon.remaining_hours ?? 0;
  if (aksiyon.overdue) {
    const gecen = Math.abs(Math.round(kalan));
    return `${gecen} ${tr.aksiyon.saatGecti}`;
  }
  if (kalan < 1) return tr.aksiyon.birSaattenAz;
  return `${Math.round(kalan)} ${tr.aksiyon.saatKaldi}`;
}

/**
 * SCR-W-09 · Aksiyonlar. v1'de aksiyon iki durumlu (açık/kapalı);
 * durum makinesi ve onaylı kapanış v1.1'de (ADR-0008). Kapanış notu
 * zorunlu: "kapattım" demek yetmez, ne yapıldığı yazılır (FR-0904).
 */
export function AksiyonlarSayfasi() {
  const [durum, setDurum] = useState<'open' | 'closed' | 'all'>('open');
  const [yalnizGecikmis, setYalnizGecikmis] = useState(false);

  const sayaclar = useQuery({ queryKey: ['aksiyon-sayac'], queryFn: aksiyonSayaclari });
  const aksiyonlar = useQuery({
    queryKey: ['aksiyonlar', { durum, yalnizGecikmis }],
    queryFn: () => aksiyonListesi({ durum, yalnizGecikmis }),
  });

  return (
    <div>
      <h1 style={{ fontSize: 'var(--baslik-bolum)', margin: '0 0 var(--bosluk-3)' }}>
        {tr.aksiyon.baslik}
      </h1>

      {sayaclar.data && (
        <div
          style={{
            display: 'flex',
            gap: 'var(--bosluk-2)',
            flexWrap: 'wrap',
            marginBottom: 'var(--bosluk-4)',
          }}
        >
          <Cip renk="nötr" metin={`${sayaclar.data.open} ${tr.aksiyon.acik}`} />
          <Cip
            renk={sayaclar.data.overdue > 0 ? 'kritik' : 'nötr'}
            ikon={sayaclar.data.overdue > 0 ? '!' : undefined}
            metin={`${sayaclar.data.overdue} ${tr.aksiyon.gecikmis}`}
          />
          <Cip
            renk={sayaclar.data.critical > 0 ? 'uyari' : 'nötr'}
            metin={`${sayaclar.data.critical} ${tr.aksiyon.kritikAdet}`}
          />
        </div>
      )}

      <div
        style={{
          display: 'flex',
          gap: 'var(--bosluk-3)',
          flexWrap: 'wrap',
          marginBottom: 'var(--bosluk-3)',
        }}
      >
        <label style={etiket}>
          {tr.aksiyon.durum}
          <select
            value={durum}
            onChange={(o) => setDurum(o.target.value as typeof durum)}
            style={alan}
          >
            <option value="open">{tr.aksiyon.acikKayitlar}</option>
            <option value="closed">{tr.aksiyon.kapaliKayitlar}</option>
            <option value="all">{tr.personel.hepsi}</option>
          </select>
        </label>
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
            checked={yalnizGecikmis}
            onChange={(o) => setYalnizGecikmis(o.target.checked)}
          />
          {tr.aksiyon.yalnizGecikmis}
        </label>
      </div>

      {aksiyonlar.isPending && <p style={{ color: 'var(--renk-sessiz)' }}>{tr.genel.yukleniyor}</p>}
      {aksiyonlar.isError && (
        <p role="alert" style={{ color: 'var(--renk-kritik)' }}>
          {tr.hata.aglaBaglanilamadi}
        </p>
      )}
      {aksiyonlar.data?.length === 0 && (
        <p style={{ color: 'var(--renk-sessiz)' }}>{tr.aksiyon.bos}</p>
      )}

      <ul
        style={{
          listStyle: 'none',
          margin: 0,
          padding: 0,
          display: 'grid',
          gap: 'var(--bosluk-2)',
        }}
      >
        {aksiyonlar.data?.map((aksiyon) => (
          <AksiyonKarti key={aksiyon.id} aksiyon={aksiyon} />
        ))}
      </ul>

      <AksiyonAcFormu />
    </div>
  );
}

function AksiyonKarti({ aksiyon }: { aksiyon: AksiyonOzet }) {
  const kuyruk = useQueryClient();
  const [notAlani, setNotAlani] = useState<string | null>(null);
  const oncelik = ONCELIKLER.find((o) => o.deger === aksiyon.priority);

  const kapat = useMutation({
    mutationFn: (note: string) => aksiyonKapat(aksiyon.id, note),
    onSuccess: async () => {
      setNotAlani(null);
      await kuyruk.invalidateQueries({ queryKey: ['aksiyonlar'] });
      await kuyruk.invalidateQueries({ queryKey: ['aksiyon-sayac'] });
    },
  });
  const problem = problemCoz(kapat.error);

  return (
    <li
      style={{
        border: '1px solid',
        borderColor: aksiyon.overdue ? 'var(--renk-kritik)' : 'var(--renk-cizgi)',
        borderRadius: 'var(--kose-kart)',
        background: 'var(--renk-yuzey)',
        padding: 'var(--bosluk-3)',
      }}
    >
      <div
        style={{ display: 'flex', gap: 'var(--bosluk-2)', alignItems: 'center', flexWrap: 'wrap' }}
      >
        <Cip renk={oncelik?.renk ?? 'nötr'} metin={aksiyon.priority_label} />
        <strong style={{ flex: '1 1 220px' }}>{aksiyon.title}</strong>
        <Cip renk="nötr" metin={aksiyon.branch_name} />
        {aksiyon.status === 'open' ? (
          <span
            style={{
              fontSize: 'var(--etiket)',
              fontWeight: 600,
              color: aksiyon.overdue ? 'var(--renk-kritik)' : 'var(--renk-murekkep2)',
            }}
          >
            {vadeMetni(aksiyon)}
          </span>
        ) : (
          <Cip renk="marka" ikon="✓" metin={tr.aksiyon.kapandi} />
        )}
      </div>

      <div style={{ color: 'var(--renk-sessiz)', fontSize: 'var(--meta)', marginTop: 4 }}>
        {aksiyon.source_label}
        {aksiyon.description ? ` · ${aksiyon.description}` : ''}
      </div>

      {aksiyon.close_note && (
        <div style={{ marginTop: 'var(--bosluk-2)', fontSize: 'var(--etiket)' }}>
          <span style={{ color: 'var(--renk-sessiz)' }}>{tr.aksiyon.kapanisNotu}: </span>
          {aksiyon.close_note}
        </div>
      )}

      {aksiyon.status === 'open' &&
        (notAlani === null ? (
          <button
            type="button"
            onClick={() => setNotAlani('')}
            style={{ ...kucukDugme, marginTop: 'var(--bosluk-2)' }}
          >
            {tr.aksiyon.kapat}
          </button>
        ) : (
          <form
            onSubmit={(olay) => {
              olay.preventDefault();
              kapat.mutate(notAlani);
            }}
            style={{
              display: 'flex',
              gap: 'var(--bosluk-2)',
              marginTop: 'var(--bosluk-2)',
              flexWrap: 'wrap',
            }}
          >
            <input
              value={notAlani}
              onChange={(o) => setNotAlani(o.target.value)}
              placeholder={tr.aksiyon.notZorunlu}
              aria-label={tr.aksiyon.kapanisNotu}
              style={{ ...alan, flex: '1 1 260px' }}
              autoFocus
            />
            <button type="submit" disabled={kapat.isPending} style={anaDugme}>
              {tr.aksiyon.kapat}
            </button>
            <button type="button" onClick={() => setNotAlani(null)} style={kucukDugme}>
              {tr.aksiyon.vazgec}
            </button>
            {problem && (
              <p role="alert" style={{ width: '100%', margin: 0, color: 'var(--renk-kritik)' }}>
                {problem.errors?.length ? problem.errors[0].sebep : problem.title}
              </p>
            )}
          </form>
        ))}
    </li>
  );
}

function AksiyonAcFormu() {
  const kuyruk = useQueryClient();
  const subeler = useQuery({
    queryKey: ['subeler', { pasifDahil: false }],
    queryFn: () => subeAgaci(),
  });
  const [subeId, setSubeId] = useState('');
  const [baslik, setBaslik] = useState('');
  const [oncelik, setOncelik] = useState<Oncelik>('normal');

  const ac = useMutation({
    mutationFn: () =>
      aksiyonAc({
        branch_id: subeId,
        title: baslik,
        priority: oncelik,
        description: null,
        assignee_user_id: null,
      }),
    onSuccess: async () => {
      setBaslik('');
      await kuyruk.invalidateQueries({ queryKey: ['aksiyonlar'] });
      await kuyruk.invalidateQueries({ queryKey: ['aksiyon-sayac'] });
    },
  });

  const duzSubeler = (subeler.data ?? []).flatMap((b) => b.branches);
  const problem = problemCoz(ac.error);

  return (
    <form
      onSubmit={(olay) => {
        olay.preventDefault();
        ac.mutate();
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
      <label style={etiket}>
        {tr.aksiyon.yeniBaslik}
        <input
          value={baslik}
          onChange={(o) => setBaslik(o.target.value)}
          required
          style={{ ...alan, width: 220 }}
        />
      </label>
      <label style={etiket}>
        {tr.personel.sube}
        <select value={subeId} onChange={(o) => setSubeId(o.target.value)} required style={alan}>
          <option value="">{tr.personel.seciniz}</option>
          {duzSubeler.map((sube) => (
            <option key={sube.id} value={sube.id}>
              {sube.name}
            </option>
          ))}
        </select>
      </label>
      <label style={etiket}>
        {tr.aksiyon.oncelik}
        <select
          value={oncelik}
          onChange={(o) => setOncelik(o.target.value as Oncelik)}
          style={alan}
        >
          {ONCELIKLER.map((o) => (
            <option key={o.deger} value={o.deger}>
              {o.etiket}
            </option>
          ))}
        </select>
      </label>
      <button type="submit" disabled={ac.isPending} style={anaDugme}>
        {tr.aksiyon.ac}
      </button>
      <p style={{ width: '100%', margin: 0, color: 'var(--renk-sessiz)', fontSize: 'var(--meta)' }}>
        {tr.aksiyon.vadeNotu}
      </p>
      {problem && (
        <p role="alert" style={{ width: '100%', margin: 0, color: 'var(--renk-kritik)' }}>
          {problem.title}
        </p>
      )}
    </form>
  );
}

const etiket = { display: 'grid', gap: 'var(--bosluk-1)', fontSize: 'var(--etiket)' } as const;

const alan = {
  height: 36,
  padding: '0 var(--bosluk-2)',
  borderRadius: 'var(--kose-dugme)',
  border: '1px solid var(--renk-cizgi)',
  background: 'var(--renk-yuzey)',
  color: 'var(--renk-murekkep)',
} as const;

const kucukDugme = {
  padding: '0 var(--bosluk-3)',
  minHeight: 32,
  borderRadius: 'var(--kose-dugme)',
  border: '1px solid var(--renk-cizgi)',
  background: 'var(--renk-yuzey2)',
  color: 'var(--renk-murekkep)',
  cursor: 'pointer',
  fontSize: 'var(--etiket)',
} as const;

const anaDugme = {
  padding: '0 var(--bosluk-4)',
  minHeight: 36,
  borderRadius: 'var(--kose-dugme)',
  border: '1px solid var(--renk-marka)',
  background: 'var(--renk-marka)',
  color: '#fff',
  cursor: 'pointer',
} as const;
