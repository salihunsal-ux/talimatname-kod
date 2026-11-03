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
import { Dugme } from '../../bilesenler/Dugme';
import { Hata, Yukleniyor } from '../../bilesenler/Durum';

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
      <header className="sayfa-basligi">
        <div>
          <h1>{tr.aksiyon.baslik}</h1>
          <p className="sayfa-basligi-alt">{tr.aksiyon.altBaslik}</p>
        </div>
        {sayaclar.data && (
          <div className="cip-listesi">
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
      </header>

      <div className="suzgec-serit">
        <label className="alan-etiket">
          {tr.aksiyon.durum}
          <select
            value={durum}
            onChange={(o) => setDurum(o.target.value as typeof durum)}
            className="alan"
          >
            <option value="open">{tr.aksiyon.acikKayitlar}</option>
            <option value="closed">{tr.aksiyon.kapaliKayitlar}</option>
            <option value="all">{tr.personel.hepsi}</option>
          </select>
        </label>
        <label className="onay-etiketi">
          <input
            type="checkbox"
            checked={yalnizGecikmis}
            onChange={(o) => setYalnizGecikmis(o.target.checked)}
          />
          {tr.aksiyon.yalnizGecikmis}
        </label>
      </div>

      {aksiyonlar.isPending && <Yukleniyor />}
      {aksiyonlar.isError && <Hata metin={tr.hata.aglaBaglanilamadi} />}
      {aksiyonlar.data?.length === 0 && <p className="bos-durum">{tr.aksiyon.bos}</p>}

      <ul className="liste-yigin">
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
    <li className={aksiyon.overdue ? 'kart kart--kritik' : 'kart'}>
      <div className="yigin yigin--dar">
        <div className="kart-serit">
          <Cip renk={oncelik?.renk ?? 'nötr'} metin={aksiyon.priority_label} />
          <strong className="kart-serit-ad">{aksiyon.title}</strong>
          <Cip renk="nötr" metin={aksiyon.branch_name} />
          {aksiyon.status === 'open' ? (
            <span className={aksiyon.overdue ? 'vade-metni vade-metni--gecikmis' : 'vade-metni'}>
              {vadeMetni(aksiyon)}
            </span>
          ) : (
            <Cip renk="marka" ikon="✓" metin={tr.aksiyon.kapandi} />
          )}
        </div>

        <p className="meta">
          {aksiyon.source_label}
          {aksiyon.description ? ` · ${aksiyon.description}` : ''}
        </p>

        {aksiyon.close_note && (
          <p className="ikincil-metin">
            <span className="durum-metni">{tr.aksiyon.kapanisNotu}: </span>
            {aksiyon.close_note}
          </p>
        )}

        {aksiyon.status === 'open' &&
          (notAlani === null ? (
            <div className="kart-serit">
              <Dugme gorunum="ikincil" boyut="kucuk" type="button" onClick={() => setNotAlani('')}>
                {tr.aksiyon.kapat}
              </Dugme>
            </div>
          ) : (
            <form
              onSubmit={(olay) => {
                olay.preventDefault();
                kapat.mutate(notAlani);
              }}
              className="yigin yigin--dar"
            >
              <div className="kart-serit">
                <input
                  value={notAlani}
                  onChange={(o) => setNotAlani(o.target.value)}
                  placeholder={tr.aksiyon.notZorunlu}
                  aria-label={tr.aksiyon.kapanisNotu}
                  className="alan alan--genis"
                  autoFocus
                />
                <Dugme type="submit" disabled={kapat.isPending}>
                  {tr.aksiyon.kapat}
                </Dugme>
                <Dugme
                  gorunum="sessiz"
                  boyut="kucuk"
                  type="button"
                  onClick={() => setNotAlani(null)}
                >
                  {tr.aksiyon.vazgec}
                </Dugme>
              </div>
              {problem && (
                <p role="alert" className="bildiri bildiri--hata">
                  {problem.errors?.length ? problem.errors[0].sebep : problem.title}
                </p>
              )}
            </form>
          ))}
      </div>
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
    >
      <fieldset className="alan-grubu alan-grubu--ayri">
        <legend>{tr.aksiyon.yeniAksiyon}</legend>
        <div className="yigin yigin--dar">
          <div className="alan-sirasi">
            <label className="alan-etiket">
              {tr.aksiyon.yeniBaslik}
              <input
                value={baslik}
                onChange={(o) => setBaslik(o.target.value)}
                required
                className="alan alan--orta"
              />
            </label>
            <label className="alan-etiket">
              {tr.personel.sube}
              <select
                value={subeId}
                onChange={(o) => setSubeId(o.target.value)}
                required
                className="alan"
              >
                <option value="">{tr.personel.seciniz}</option>
                {duzSubeler.map((sube) => (
                  <option key={sube.id} value={sube.id}>
                    {sube.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="alan-etiket">
              {tr.aksiyon.oncelik}
              <select
                value={oncelik}
                onChange={(o) => setOncelik(o.target.value as Oncelik)}
                className="alan"
              >
                {ONCELIKLER.map((o) => (
                  <option key={o.deger} value={o.deger}>
                    {o.etiket}
                  </option>
                ))}
              </select>
            </label>
            <Dugme type="submit" disabled={ac.isPending}>
              {tr.aksiyon.ac}
            </Dugme>
          </div>
          <p className="alan-ipucu">{tr.aksiyon.vadeNotu}</p>
          {problem && (
            <p role="alert" className="bildiri bildiri--hata">
              {problem.title}
            </p>
          )}
        </div>
      </fieldset>
    </form>
  );
}
