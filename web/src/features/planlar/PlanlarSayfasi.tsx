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
import { tekrarMetni } from './tekrar';

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
      <header className="sayfa-basligi">
        <div>
          <h1>{tr.plan.baslik}</h1>
          <p className="sayfa-basligi-alt">{tr.plan.altBaslik}</p>
        </div>
      </header>

      {planlar.isPending && <p className="meta">{tr.genel.yukleniyor}</p>}
      {planlar.isError && (
        <p role="alert" className="bildiri bildiri--hata">
          {tr.hata.aglaBaglanilamadi}
        </p>
      )}

      {planlar.data?.length === 0 && <p className="bos-durum">{tr.plan.planYok}</p>}

      {planlar.data && planlar.data.length > 0 && (
        <div className="tablo-kaydirma">
          <table className="tablo">
            <thead>
              <tr>
                <th>{tr.plan.ad}</th>
                <th>{tr.plan.sablon}</th>
                <th>{tr.plan.tekrar}</th>
                <th>{tr.plan.pencere}</th>
                <th>{tr.plan.kapsam}</th>
                <th className="eylem">{tr.personel.islem}</th>
              </tr>
            </thead>
            <tbody>
              {planlar.data.map((plan) => (
                <tr key={plan.id}>
                  <th scope="row">
                    {plan.name}{' '}
                    {!plan.active && <Cip renk="pasif" ikon="–" metin={tr.plan.durduruldu} />}
                  </th>
                  <td className="ikincil">{plan.template_name}</td>
                  {/* Çiğ RFC 5545 kuralı yerine okunur hâli (bkz. tekrar.ts). */}
                  <td>{tekrarMetni(plan.recurrence)}</td>
                  <td className="sayisal">
                    {tr.plan.dakika(plan.duration_minutes)}
                    {plan.tolerance_minutes > 0 && (
                      <span className="meta"> {tr.plan.toleransli(plan.tolerance_minutes)}</span>
                    )}
                  </td>
                  <td>
                    {plan.branch_count} {tr.plan.sube}
                  </td>
                  <td className="eylem">
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
        </div>
      )}

      <section className="yigin yigin--dar alan-grubu--ayri">
        <h2 className="baslik-bolum">{tr.plan.bugun}</h2>
        {bugun.data?.length === 0 && <p className="bos-durum">{tr.plan.bugunBos}</p>}
        <ul className="liste-yigin">
          {bugun.data?.map((run) => {
            const cip = DURUM_CIPI[run.status] ?? DURUM_CIPI.scheduled;
            return (
              /* Tıklanmayan satır, tıklananla aynı ritimde: ölçüler
                 `.liste-satiri`den geliyor, yalnızca hâlleri kapalı. */
              <li key={run.id} className="liste-satiri liste-satiri--durgun">
                <strong className="liste-satiri-ad">{run.branch_name}</strong>
                <span className="sayisal ikincil-metin">
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
  const gunIciAcik = baslangicTuru === 'fixed' && tekrar !== 'once';

  return (
    <section className="yigin yigin--dar alan-grubu--ayri">
      <h2 className="baslik-bolum">{tr.plan.yeniPlan}</h2>

      {/* Alanlar dört gruba ayrıldı. Hepsi tek bir `flex-wrap` satırında
          dururken koşullu alanlar her seçimde sırayı yeniden akıtıyor,
          "Saat" ile "Çıpa" sayfanın iki ucuna düşebiliyordu. Grup aynı
          zamanda ekran okuyucuda duyurulan bir sınır (fieldset). */}
      <div className="yigin yigin--dar">
        <fieldset className="alan-grubu">
          <legend>{tr.plan.grupNe}</legend>
          <div className="alan-sirasi">
            <label className="alan-etiket alan-etiket--genis">
              {tr.plan.ad}
              <input value={ad} onChange={(o) => setAd(o.target.value)} className="alan" />
            </label>

            <label className="alan-etiket alan-etiket--genis">
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
          </div>
        </fieldset>

        <fieldset className="alan-grubu">
          <legend>{tr.plan.grupNeZaman}</legend>
          <div className="alan-sirasi">
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
              <fieldset className="alan-kumesi">
                <legend className="alan-etiket">{tr.plan.gunler}</legend>
                <div className="cip-listesi">
                  {GUNLER.map((g, i) => (
                    <label key={g} className="secim-cipi">
                      <input
                        type="checkbox"
                        checked={gunler.includes(i)}
                        onChange={(o) =>
                          setGunler(
                            o.target.checked ? [...gunler, i] : gunler.filter((x) => x !== i),
                          )
                        }
                        aria-label={g}
                      />
                      {g}
                    </label>
                  ))}
                </div>
              </fieldset>
            )}

            {tekrar === 'monthly' && (
              <>
                <label className="alan-etiket">
                  {tr.plan.aylik}
                  <select
                    value={ayKurali}
                    onChange={(o) => setAyKurali(o.target.value as typeof ayKurali)}
                    className="alan"
                  >
                    <option value="gun">{tr.plan.ayinGunu}</option>
                    <option value="ninci">{tr.plan.nInciHaftaGunu}</option>
                  </select>
                </label>
                {ayKurali === 'gun' ? (
                  <label className="alan-etiket">
                    {tr.plan.ayinGunu}
                    <input
                      type="number"
                      min={1}
                      max={31}
                      value={ayinGunu}
                      onChange={(o) => setAyinGunu(Number(o.target.value))}
                      aria-label={tr.plan.ayinGunu}
                      className="alan alan--sayi"
                    />
                  </label>
                ) : (
                  <>
                    <label className="alan-etiket">
                      {tr.plan.nInciHaftaGunu}
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
                    </label>
                    <label className="alan-etiket">
                      {tr.plan.gunler}
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
                    </label>
                  </>
                )}
              </>
            )}

            {gunIciAcik && (
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

            {gunIciAcik && gunIci === 'liste' && (
              <fieldset className="alan-kumesi">
                <legend className="alan-etiket">{tr.plan.saatListesi}</legend>
                <div className="cip-listesi">
                  {saatler.map((saat, i) => (
                    <span key={i} className="kart-serit">
                      <input
                        type="time"
                        value={saat}
                        onChange={(o) =>
                          setSaatler(saatler.map((x, j) => (i === j ? o.target.value : x)))
                        }
                        aria-label={tr.plan.saatListesi + ' ' + (i + 1)}
                        className="alan alan--saat"
                      />
                      <Dugme
                        gorunum="sessiz"
                        boyut="kucuk"
                        type="button"
                        aria-label={tr.plan.saatSil}
                        onClick={() => setSaatler(saatler.filter((_, j) => j !== i))}
                      >
                        ✕
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

            {gunIciAcik && gunIci === 'aralik' && (
              <>
                <label className="alan-etiket">
                  {tr.plan.araSaat}
                  <input
                    type="number"
                    min={1}
                    max={12}
                    value={araSaat}
                    onChange={(o) => setAraSaat(Number(o.target.value))}
                    className="alan alan--sayi"
                  />
                </label>
                <label className="alan-etiket">
                  {tr.plan.gunIciBitis}
                  <input
                    type="time"
                    value={gunIciBitis}
                    onChange={(o) => setGunIciBitis(o.target.value)}
                    className="alan alan--saat"
                  />
                </label>
              </>
            )}

            {tekrar !== 'once' && (
              <label className="alan-etiket">
                {tr.plan.bitisTarihi}
                <input
                  type="date"
                  value={bitisTarihi}
                  onChange={(o) => setBitisTarihi(o.target.value)}
                  className="alan alan--otomatik"
                />
              </label>
            )}
          </div>
        </fieldset>

        <fieldset className="alan-grubu">
          <legend>{tr.plan.grupPencere}</legend>
          <div className="alan-sirasi">
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
                  className="alan alan--saat"
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
                    className="alan alan--sayi"
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
                className="alan alan--sayi"
              />
            </label>
            <label className="alan-etiket">
              {tr.plan.tolerans}
              <input
                type="number"
                value={tolerans}
                min={0}
                onChange={(o) => setTolerans(Number(o.target.value))}
                className="alan alan--sayi"
              />
            </label>
          </div>
        </fieldset>

        <fieldset className="alan-grubu">
          <legend>{tr.plan.kapsam}</legend>
          <div className="cip-listesi">
            {duzSubeler.map((sube) => (
              <label key={sube.id} className="secim-cipi">
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
                />
                {sube.name}
              </label>
            ))}
          </div>
        </fieldset>
      </div>

      <div className="eylemler">
        {/* Önizleme birincil: kaydetmeden önce yapılması istenen iş bu. */}
        <Dugme
          type="button"
          disabled={!hazir || onizleme.isPending}
          onClick={() => onizleme.mutate()}
        >
          {tr.plan.onizle}
        </Dugme>
        <Dugme
          gorunum="ikincil"
          type="button"
          disabled={!hazir || olustur.isPending}
          onClick={() => olustur.mutate()}
        >
          {tr.plan.kaydet}
        </Dugme>
      </div>

      {problem && (
        <p role="alert" className="bildiri bildiri--hata">
          {problem.title}
          {problem.errors?.length ? `: ${problem.errors[0].sebep}` : ''}
        </p>
      )}

      {onizleme.data && (
        <div role="status" className="kart yigin yigin--dar">
          <strong>
            {tr.plan.onizlemeBasligi} ({onizleme.data.days} {tr.plan.gun}):{' '}
            {onizleme.data.run_count} {tr.plan.calistirma}
          </strong>
          {onizleme.data.run_count === 0 && (
            <p className="bildiri bildiri--uyari">{tr.plan.onizlemeBos}</p>
          )}
          <ul className="madde-listesi ikincil-metin">
            {onizleme.data.runs.slice(0, 12).map((run) => (
              <li key={run.id} className="sayisal">
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
