import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { problemCoz } from '../../api/client';
import {
  gununCalistirmalari,
  planBaslat,
  planDurdur,
  planListesi,
  planOlustur,
  planOnizleme,
  type PlanGirdisi,
} from '../../api/planlar';
import { sablonListesi } from '../../api/sablonlar';
import { subeAgaci } from '../../api/subeler';
import { Cip } from '../../bilesenler/Cip';
import { useYonetici } from '../../api/yetki';
import { tr } from '../../i18n/tr';
import { Dugme } from '../../bilesenler/Dugme';

const GUNLER = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'];

const DURUM_CIPI: Record<string, { renk: 'marka' | 'uyari' | 'kritik' | 'pasif'; ikon: string }> = {
  scheduled: { renk: 'pasif', ikon: '○' },
  in_progress: { renk: 'uyari', ikon: '◐' },
  submitted: { renk: 'marka', ikon: '✓' },
  missed: { renk: 'kritik', ikon: '✕' },
  cancelled: { renk: 'pasif', ikon: '–' },
};

function saat(iso: string): string {
  return new Date(iso).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
}

function gunAdi(isoTarih: string): string {
  return new Date(`${isoTarih}T12:00:00`).toLocaleDateString('tr-TR', {
    day: 'numeric',
    month: 'short',
    weekday: 'short',
  });
}

/**
 * SCR-W-06 · Planlar: plan listesi, bugünün çalıştırmaları ve yeni plan
 * formu + **7 gün önizleme** (FR-0511). Önizleme kaydetmeden çalışır:
 * kullanıcı kuralı yanlış kurduysa bunu plan kaydedilmeden görür.
 */
export function PlanlarSayfasi() {
  const yonetici = useYonetici();
  const planlar = useQuery({ queryKey: ['planlar'], queryFn: () => planListesi(true) });
  const bugun = useQuery({ queryKey: ['calistirmalar'], queryFn: () => gununCalistirmalari() });
  const kuyruk = useQueryClient();
  const baslat = useMutation({
    mutationFn: planBaslat,
    onSuccess: () => void kuyruk.invalidateQueries({ queryKey: ['planlar'] }),
  });
  const durdur = useMutation({
    mutationFn: planDurdur,
    onSuccess: async () => {
      await kuyruk.invalidateQueries({ queryKey: ['planlar'] });
      await kuyruk.invalidateQueries({ queryKey: ['calistirmalar'] });
    },
  });

  return (
    <div>
      <h1 style={{ fontSize: 'var(--baslik-ekran)', margin: '0 0 var(--bosluk-3)' }}>
        {tr.plan.baslik}
      </h1>

      {planlar.isPending && <p style={{ color: 'var(--renk-sessiz)' }}>{tr.genel.yukleniyor}</p>}
      {planlar.isError && (
        <p role="alert" style={{ color: 'var(--renk-kritik)' }}>
          {tr.hata.aglaBaglanilamadi}
        </p>
      )}

      {planlar.data && (
        <table className="tablo">
          <thead>
            <tr
              style={{ textAlign: 'left', color: 'var(--renk-sessiz)', fontSize: 'var(--etiket)' }}
            >
              <th style={{ padding: '6px 0' }}>{tr.plan.ad}</th>
              <th>{tr.plan.sablon}</th>
              <th>{tr.plan.tekrar}</th>
              <th>{tr.plan.kapsam}</th>
              <th style={{ textAlign: 'right' }}>{tr.personel.islem}</th>
            </tr>
          </thead>
          <tbody>
            {planlar.data.map((plan) => (
              <tr key={plan.id} style={{ borderTop: '1px solid var(--renk-cizgi)' }}>
                <td style={{ padding: '10px 0' }}>
                  {plan.name}{' '}
                  {!plan.active && <Cip renk="pasif" ikon="–" metin={tr.plan.durduruldu} />}
                </td>
                <td style={{ color: 'var(--renk-murekkep2)' }}>{plan.template_name}</td>
                <td style={{ fontSize: 'var(--etiket)', color: 'var(--renk-murekkep2)' }}>
                  {plan.recurrence} · {plan.duration_minutes} dk
                  {plan.tolerance_minutes > 0 && ` (+${plan.tolerance_minutes} tolerans)`}
                </td>
                <td>
                  {plan.branch_count} {tr.plan.sube}
                </td>
                <td style={{ textAlign: 'right' }}>
                  {yonetici && (
                    <Dugme
                      gorunum="ikincil"
                      boyut="kucuk"
                      type="button"
                      onClick={() =>
                        plan.active ? durdur.mutate(plan.id) : baslat.mutate(plan.id)
                      }
                    >
                      {plan.active ? tr.plan.durdur : tr.plan.baslat}
                    </Dugme>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <section style={{ marginTop: 'var(--bosluk-6)' }}>
        <h2 style={{ fontSize: 'var(--baslik-bolum)', margin: '0 0 var(--bosluk-2)' }}>
          {tr.plan.bugun}
        </h2>
        {bugun.data?.length === 0 && (
          <p style={{ color: 'var(--renk-sessiz)' }}>{tr.plan.bugunBos}</p>
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
          {bugun.data?.map((run) => {
            const cip = DURUM_CIPI[run.status] ?? DURUM_CIPI.scheduled;
            return (
              <li
                key={run.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--bosluk-3)',
                  flexWrap: 'wrap',
                  padding: 'var(--bosluk-2) var(--bosluk-3)',
                  border: '1px solid var(--renk-cizgi)',
                  borderRadius: 'var(--kose-dugme)',
                  background: 'var(--renk-yuzey)',
                }}
              >
                <strong style={{ flex: '1 1 140px' }}>{run.branch_name}</strong>
                <span
                  style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--renk-murekkep2)' }}
                >
                  {saat(run.window_start)} – {saat(run.window_end)}
                </span>
                <Cip
                  renk={cip.renk}
                  ikon={cip.ikon}
                  metin={
                    tr.plan.durumlar[run.status as keyof typeof tr.plan.durumlar] ?? run.status
                  }
                />
                {run.late && <Cip renk="uyari" ikon="⏱" metin={tr.plan.gec} />}
              </li>
            );
          })}
        </ul>
      </section>

      {yonetici && <PlanFormu />}
    </div>
  );
}

function PlanFormu() {
  const kuyruk = useQueryClient();
  const sablonlar = useQuery({ queryKey: ['sablonlar'], queryFn: sablonListesi });
  const subeler = useQuery({
    queryKey: ['subeler', { pasifDahil: false }],
    queryFn: () => subeAgaci(),
  });

  const [ad, setAd] = useState('');
  const [surumId, setSurumId] = useState('');
  const [seciliSubeler, setSeciliSubeler] = useState<string[]>([]);
  const [tekrar, setTekrar] = useState<'daily' | 'weekly' | 'monthly' | 'once'>('daily');
  const [gunler, setGunler] = useState<number[]>([0]);
  const [ayKurali, setAyKurali] = useState<'gun' | 'ninci'>('gun');
  const [ayinGunu, setAyinGunu] = useState(1);
  const [ninci, setNinci] = useState(1);
  const [ayHaftaGunu, setAyHaftaGunu] = useState(0);
  const [gunIci, setGunIci] = useState<'yok' | 'liste' | 'aralik'>('yok');
  const [saatler, setSaatler] = useState<string[]>(['09:00', '14:00']);
  const [araSaat, setAraSaat] = useState(2);
  const [gunIciBitis, setGunIciBitis] = useState('18:00');
  const [bitisTarihi, setBitisTarihi] = useState('');
  const [baslangicTuru, setBaslangicTuru] = useState<'fixed' | 'anchor'>('fixed');
  const [saatDegeri, setSaatDegeri] = useState('22:00');
  const [cipa, setCipa] = useState<'open' | 'close'>('close');
  const [ofset, setOfset] = useState(-60);
  const [sure, setSure] = useState(120);
  const [tolerans, setTolerans] = useState(30);

  const yayindakiSurumler = (sablonlar.data ?? []).flatMap((s) =>
    s.versions.filter((v) => v.status === 'published').map((v) => ({ ...v, name: s.name })),
  );
  const duzSubeler = (subeler.data ?? []).flatMap((b) => b.branches);

  const girdi: PlanGirdisi = {
    name: ad,
    template_version_id: surumId,
    branch_ids: seciliSubeler,
    schedule: {
      repeat: tekrar,
      weekdays: gunler,
      times: gunIci === 'liste' ? saatler.map((x) => x + ':00') : [],
      every_hours: gunIci === 'aralik' ? araSaat : null,
      until_time: gunIci === 'aralik' ? gunIciBitis + ':00' : null,
      month_day: tekrar === 'monthly' && ayKurali === 'gun' ? ayinGunu : null,
      month_nth: tekrar === 'monthly' && ayKurali === 'ninci' ? ninci : null,
      month_weekday: tekrar === 'monthly' && ayKurali === 'ninci' ? ayHaftaGunu : null,
      ends_on: bitisTarihi === '' ? null : bitisTarihi,
      starts_on: new Date().toISOString().slice(0, 10),
      start_mode: baslangicTuru,
      start_time: baslangicTuru === 'fixed' ? `${saatDegeri}:00` : null,
      anchor_reference: baslangicTuru === 'anchor' ? cipa : null,
      anchor_offset_minutes: ofset,
      duration_minutes: sure,
      tolerance_minutes: tolerans,
    },
    assignment: { kind: 'anyone', role: null, user_id: null },
  };

  const hazir = ad.trim() !== '' && surumId !== '' && seciliSubeler.length > 0;

  const onizleme = useMutation({ mutationFn: () => planOnizleme(girdi) });
  const olustur = useMutation({
    mutationFn: () => planOlustur(girdi),
    onSuccess: async () => {
      setAd('');
      setSeciliSubeler([]);
      onizleme.reset();
      await kuyruk.invalidateQueries({ queryKey: ['planlar'] });
      await kuyruk.invalidateQueries({ queryKey: ['calistirmalar'] });
    },
  });

  const problem = problemCoz(olustur.error) ?? problemCoz(onizleme.error);

  return (
    <section
      style={{
        marginTop: 'var(--bosluk-6)',
        paddingTop: 'var(--bosluk-4)',
        borderTop: '1px solid var(--renk-cizgi)',
      }}
    >
      <h2 style={{ fontSize: 'var(--baslik-bolum)', margin: '0 0 var(--bosluk-3)' }}>
        {tr.plan.yeniPlan}
      </h2>

      <div
        style={{
          display: 'flex',
          gap: 'var(--bosluk-3)',
          flexWrap: 'wrap',
          alignItems: 'flex-end',
        }}
      >
        <label className="alan-etiket">
          {tr.plan.ad}
          <input
            value={ad}
            onChange={(o) => setAd(o.target.value)}
            className="alan"
            style={{ width: 180 }}
          />
        </label>

        <label className="alan-etiket">
          {tr.plan.sablon}
          <select value={surumId} onChange={(o) => setSurumId(o.target.value)} className="alan">
            <option value="">{tr.personel.seciniz}</option>
            {yayindakiSurumler.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name} · {tr.sablon.surum} {v.version_no}
              </option>
            ))}
          </select>
        </label>

        <label className="alan-etiket">
          {tr.plan.tekrar}
          <select
            value={tekrar}
            onChange={(o) => setTekrar(o.target.value as typeof tekrar)}
            className="alan"
          >
            <option value="daily">{tr.plan.herGun}</option>
            <option value="weekly">{tr.plan.haftalik}</option>
            <option value="monthly">{tr.plan.aylik}</option>
            <option value="once">{tr.plan.tekSeferlik}</option>
          </select>
        </label>

        {tekrar === 'weekly' && (
          <fieldset style={{ border: 'none', padding: 0, margin: 0, display: 'flex', gap: 4 }}>
            <legend className="sr-only">{tr.plan.gunler}</legend>
            {GUNLER.map((g, i) => (
              <label key={g} style={secimCipi(gunler.includes(i))}>
                <input
                  type="checkbox"
                  checked={gunler.includes(i)}
                  onChange={(o) =>
                    setGunler(o.target.checked ? [...gunler, i] : gunler.filter((x) => x !== i))
                  }
                  aria-label={g}
                  style={{ margin: 0 }}
                />
                {g}
              </label>
            ))}
          </fieldset>
        )}

        {tekrar === 'monthly' && (
          <label className="alan-etiket">
            {tr.plan.aylik}
            <div style={{ display: 'flex', gap: 'var(--bosluk-2)' }}>
              <select
                value={ayKurali}
                onChange={(o) => setAyKurali(o.target.value as typeof ayKurali)}
                className="alan"
              >
                <option value="gun">{tr.plan.ayinGunu}</option>
                <option value="ninci">{tr.plan.nInciHaftaGunu}</option>
              </select>
              {ayKurali === 'gun' ? (
                <input
                  type="number"
                  min={1}
                  max={31}
                  value={ayinGunu}
                  onChange={(o) => setAyinGunu(Number(o.target.value))}
                  aria-label={tr.plan.ayinGunu}
                  className="alan"
                />
              ) : (
                <>
                  <select
                    value={ninci}
                    onChange={(o) => setNinci(Number(o.target.value))}
                    aria-label={tr.plan.nInciHaftaGunu}
                    className="alan"
                  >
                    {tr.plan.ninci.map((ad, i) => (
                      <option key={ad} value={i === 4 ? -1 : i + 1}>
                        {ad}
                      </option>
                    ))}
                  </select>
                  <select
                    value={ayHaftaGunu}
                    onChange={(o) => setAyHaftaGunu(Number(o.target.value))}
                    aria-label={tr.plan.gunler}
                    className="alan"
                  >
                    {GUNLER.map((g, i) => (
                      <option key={g} value={i}>
                        {g}
                      </option>
                    ))}
                  </select>
                </>
              )}
            </div>
          </label>
        )}

        {baslangicTuru === 'fixed' && tekrar !== 'once' && (
          <label className="alan-etiket">
            {tr.plan.gunIci}
            <select
              value={gunIci}
              onChange={(o) => setGunIci(o.target.value as typeof gunIci)}
              className="alan"
            >
              <option value="yok">{tr.plan.gunIciYok}</option>
              <option value="liste">{tr.plan.saatListesi}</option>
              <option value="aralik">{tr.plan.herNSaat}</option>
            </select>
          </label>
        )}

        {baslangicTuru === 'fixed' && tekrar !== 'once' && gunIci === 'liste' && (
          <fieldset style={{ border: 'none', padding: 0, margin: 0 }}>
            <legend className="alan-etiket">{tr.plan.saatListesi}</legend>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--bosluk-2)' }}>
              {saatler.map((saat, i) => (
                <span key={i} style={{ display: 'flex', gap: 4 }}>
                  <input
                    type="time"
                    value={saat}
                    onChange={(o) =>
                      setSaatler(saatler.map((x, j) => (i === j ? o.target.value : x)))
                    }
                    aria-label={tr.plan.saatListesi + ' ' + (i + 1)}
                    className="alan"
                  />
                  <Dugme
                    gorunum="ikincil"
                    boyut="kucuk"
                    type="button"
                    aria-label={tr.plan.saatSil}
                    onClick={() => setSaatler(saatler.filter((_, j) => j !== i))}
                  >
                    x
                  </Dugme>
                </span>
              ))}
              <Dugme
                gorunum="ikincil"
                boyut="kucuk"
                type="button"
                onClick={() => setSaatler([...saatler, '12:00'])}
              >
                {tr.plan.saatEkle}
              </Dugme>
            </div>
          </fieldset>
        )}

        {baslangicTuru === 'fixed' && tekrar !== 'once' && gunIci === 'aralik' && (
          <div style={{ display: 'flex', gap: 'var(--bosluk-3)' }}>
            <label className="alan-etiket">
              {tr.plan.araSaat}
              <input
                type="number"
                min={1}
                max={12}
                value={araSaat}
                onChange={(o) => setAraSaat(Number(o.target.value))}
                className="alan"
              />
            </label>
            <label className="alan-etiket">
              {tr.plan.gunIciBitis}
              <input
                type="time"
                value={gunIciBitis}
                onChange={(o) => setGunIciBitis(o.target.value)}
                className="alan"
              />
            </label>
          </div>
        )}

        {tekrar !== 'once' && (
          <label className="alan-etiket">
            {tr.plan.bitisTarihi}
            <input
              type="date"
              value={bitisTarihi}
              onChange={(o) => setBitisTarihi(o.target.value)}
              className="alan"
            />
          </label>
        )}

        <label className="alan-etiket">
          {tr.plan.baslangic}
          <select
            value={baslangicTuru}
            onChange={(o) => setBaslangicTuru(o.target.value as typeof baslangicTuru)}
            className="alan"
          >
            <option value="fixed">{tr.plan.sabitSaat}</option>
            <option value="anchor">{tr.plan.calismaSaatinden}</option>
          </select>
        </label>

        {baslangicTuru === 'fixed' ? (
          <label className="alan-etiket">
            {tr.plan.saat}
            <input
              type="time"
              value={saatDegeri}
              onChange={(o) => setSaatDegeri(o.target.value)}
              className="alan"
              style={{ width: 110 }}
            />
          </label>
        ) : (
          <>
            <label className="alan-etiket">
              {tr.plan.cipa}
              <select
                value={cipa}
                onChange={(o) => setCipa(o.target.value as typeof cipa)}
                className="alan"
              >
                <option value="open">{tr.plan.acilis}</option>
                <option value="close">{tr.plan.kapanis}</option>
              </select>
            </label>
            <label className="alan-etiket">
              {tr.plan.ofset}
              <input
                type="number"
                value={ofset}
                step={15}
                onChange={(o) => setOfset(Number(o.target.value))}
                className="alan"
                style={{ width: 90 }}
              />
            </label>
          </>
        )}

        <label className="alan-etiket">
          {tr.plan.sure}
          <input
            type="number"
            value={sure}
            min={1}
            onChange={(o) => setSure(Number(o.target.value))}
            className="alan"
            style={{ width: 90 }}
          />
        </label>
        <label className="alan-etiket">
          {tr.plan.tolerans}
          <input
            type="number"
            value={tolerans}
            min={0}
            onChange={(o) => setTolerans(Number(o.target.value))}
            className="alan"
            style={{ width: 90 }}
          />
        </label>
      </div>

      <fieldset
        style={{
          border: '1px solid var(--renk-cizgi)',
          borderRadius: 'var(--kose-dugme)',
          marginTop: 'var(--bosluk-3)',
          padding: 'var(--bosluk-3)',
        }}
      >
        <legend style={{ fontSize: 'var(--etiket)', color: 'var(--renk-sessiz)' }}>
          {tr.plan.kapsam}
        </legend>
        <div style={{ display: 'flex', gap: 'var(--bosluk-3)', flexWrap: 'wrap' }}>
          {duzSubeler.map((sube) => (
            <label key={sube.id} style={secimCipi(seciliSubeler.includes(sube.id))}>
              <input
                type="checkbox"
                checked={seciliSubeler.includes(sube.id)}
                onChange={(o) =>
                  setSeciliSubeler(
                    o.target.checked
                      ? [...seciliSubeler, sube.id]
                      : seciliSubeler.filter((x) => x !== sube.id),
                  )
                }
                aria-label={sube.name}
                style={{ margin: 0 }}
              />
              {sube.name}
            </label>
          ))}
        </div>
      </fieldset>

      <div
        style={{
          display: 'flex',
          gap: 'var(--bosluk-2)',
          marginTop: 'var(--bosluk-3)',
          flexWrap: 'wrap',
        }}
      >
        <Dugme
          gorunum="ikincil"
          boyut="kucuk"
          type="button"
          disabled={!hazir || onizleme.isPending}
          onClick={() => onizleme.mutate()}
          style={{ minHeight: 40, opacity: hazir ? 1 : 0.5 }}
        >
          {tr.plan.onizle}
        </Dugme>
        <Dugme
          type="button"
          disabled={!hazir || olustur.isPending}
          onClick={() => olustur.mutate()}
          style={{ opacity: hazir ? 1 : 0.5 }}
        >
          {tr.plan.kaydet}
        </Dugme>
      </div>

      {problem && (
        <p role="alert" style={{ color: 'var(--renk-kritik)' }}>
          {problem.title}
          {problem.errors?.length ? `: ${problem.errors[0].sebep}` : ''}
        </p>
      )}

      {onizleme.data && (
        <div role="status" style={{ marginTop: 'var(--bosluk-3)' }}>
          <strong>
            {tr.plan.onizlemeBasligi} ({onizleme.data.days} {tr.plan.gun}):{' '}
            {onizleme.data.run_count} {tr.plan.calistirma}
          </strong>
          {onizleme.data.run_count === 0 && (
            <p style={{ color: 'var(--renk-uyari)' }}>{tr.plan.onizlemeBos}</p>
          )}
          <ul
            style={{
              margin: 'var(--bosluk-2) 0 0',
              paddingLeft: 'var(--bosluk-4)',
              fontSize: 'var(--etiket)',
            }}
          >
            {onizleme.data.runs.slice(0, 12).map((run) => (
              <li key={run.id} style={{ fontVariantNumeric: 'tabular-nums' }}>
                {gunAdi(run.business_day)} · {run.branch_name} · {saat(run.window_start)}–
                {saat(run.window_end)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

/** Seçilebilir çip: kutunun kendisi küçük, tıklanabilir alan büyük (NFR-11). */
function secimCipi(secili: boolean) {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 'var(--bosluk-2)',
    minHeight: 36,
    padding: '0 var(--bosluk-3)',
    borderRadius: 'var(--kose-cip)',
    border: '1px solid',
    borderColor: secili ? 'var(--renk-marka)' : 'var(--renk-cizgi)',
    background: secili ? 'var(--renk-marka-acik)' : 'var(--renk-yuzey)',
    color: secili ? 'var(--renk-marka)' : 'var(--renk-murekkep2)',
    fontSize: 'var(--etiket)',
    cursor: 'pointer',
  } as const;
}
