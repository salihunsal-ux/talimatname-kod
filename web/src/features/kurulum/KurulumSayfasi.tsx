import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { problemCoz } from '../../api/client';
import {
  hataRaporuIndir,
  kurulumDurumu,
  kurulumYayinla,
  kutuphane,
  markaKaydet,
  planOlustur,
  planOnerisi,
  personelOnizle,
  personelSablonuIndir,
  personelYukle,
  sablonIndir,
  sablonKopyala,
  subeOnizle,
  subeYukle,
  type KurulumDurumu,
  type Yukleme,
  type YuklemeRaporu,
} from '../../api/kurulum';
import { Cip } from '../../bilesenler/Cip';
import { tr } from '../../i18n/tr';
import { Dugme } from '../../bilesenler/Dugme';

/**
 * SCR-W-01 · Kurulum sihirbazı (FR-1401).
 *
 * Adım çubuğu **veriden** okunuyor: sunucu hangi adımın bittiğini
 * sayarak söylüyor, panel sayaç tutmuyor. Tarayıcı kapanıp açılınca
 * kullanıcı kaldığı adımda buluyor kendini (TC-004) — çünkü saklanan
 * bir "adım" yok, durumun kendisi var.
 */
export function KurulumSayfasi() {
  const istemci = useQueryClient();
  const durum = useQuery({ queryKey: ['kurulum'], queryFn: kurulumDurumu });
  const [acik, setAcik] = useState<string | null>(null);

  if (durum.isPending) return <p style={{ color: 'var(--renk-sessiz)' }}>{tr.genel.yukleniyor}</p>;
  if (durum.isError || !durum.data)
    return (
      <p role="alert" style={{ color: 'var(--renk-kritik)' }}>
        {tr.hata.aglaBaglanilamadi}
      </p>
    );

  const veri = durum.data;
  const secili = acik ?? veri.current;
  const yenile = () => istemci.invalidateQueries({ queryKey: ['kurulum'] });

  return (
    <div style={{ maxWidth: 860 }}>
      <h1 style={{ fontSize: 'var(--baslik-ekran)', margin: 0 }}>{tr.kurulum.baslik}</h1>
      <p style={{ color: 'var(--renk-murekkep2)', marginTop: 'var(--bosluk-2)' }}>
        {tr.kurulum.aciklama}
      </p>

      <AdimCubugu durum={veri} secili={secili} onSec={setAcik} />

      <section
        style={{
          border: '1px solid var(--renk-cizgi)',
          borderRadius: 'var(--kose-kart)',
          padding: 'var(--bosluk-4)',
          background: 'var(--renk-yuzey)',
        }}
      >
        {secili === 'brand' && <MarkaAdimi durum={veri} onKaydedildi={yenile} />}
        {secili === 'branches' && (
          <YuklemeAdimi
            tur="branches"
            baslik={tr.kurulum.subeBaslik}
            aciklama={tr.kurulum.subeAciklama}
            sablonEtiketi={tr.kurulum.sablonIndir}
            yukleEtiketi={tr.kurulum.subeleriYukle}
            sablon={sablonIndir}
            onizleyici={subeOnizle}
            yukleyici={subeYukle}
            onYuklendi={yenile}
          />
        )}
        {secili === 'template' && <SablonAdimi onSecildi={yenile} />}
        {secili === 'plan' && <PlanAdimi onKaydedildi={yenile} />}
        {secili === 'staff' && (
          <YuklemeAdimi
            tur="staff"
            baslik={tr.kurulum.personelBaslik}
            aciklama={tr.kurulum.personelAciklama}
            sablonEtiketi={tr.kurulum.personelSablonu}
            yukleEtiketi={tr.kurulum.personeliDavetEt}
            sablon={personelSablonuIndir}
            onizleyici={personelOnizle}
            yukleyici={personelYukle}
            onYuklendi={yenile}
          />
        )}
        {secili === 'review' && <SonrakiAdimlar adim={secili} durum={veri} onTamamla={yenile} />}
      </section>
    </div>
  );
}

function AdimCubugu({
  durum,
  secili,
  onSec,
}: {
  durum: KurulumDurumu;
  secili: string;
  onSec: (adim: string) => void;
}) {
  return (
    <ol
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 'var(--bosluk-2)',
        listStyle: 'none',
        padding: 0,
        margin: 'var(--bosluk-4) 0',
      }}
    >
      {durum.steps.map((adim, sira) => {
        const aktif = adim.step === secili;
        return (
          <li key={adim.step}>
            <Dugme
              type="button"
              onClick={() => onSec(adim.step)}
              aria-current={aktif ? 'step' : undefined}
            >
              <span aria-hidden="true">{adim.done ? '✓' : sira + 1}</span>
              <span>{adim.label}</span>
              {adim.done && <span className="sr-only">{tr.kurulum.tamamlandi}</span>}
            </Dugme>
          </li>
        );
      })}
    </ol>
  );
}

function MarkaAdimi({ durum, onKaydedildi }: { durum: KurulumDurumu; onKaydedildi: () => void }) {
  const marka = durum.brand;
  const [ad, setAd] = useState(marka?.brand_name ?? '');
  const [dilim, setDilim] = useState(marka?.timezone ?? 'Europe/Istanbul');
  const [acilis, setAcilis] = useState(marka?.hours?.[0]?.open_time?.slice(0, 5) ?? '09:00');
  const [kapanis, setKapanis] = useState(marka?.hours?.[0]?.close_time?.slice(0, 5) ?? '23:30');
  const [kapali, setKapali] = useState<number[]>(
    (marka?.hours ?? []).filter((s) => s.open_time === null).map((s) => s.weekday),
  );

  const kaydet = useMutation({
    mutationFn: () =>
      markaKaydet({
        brand_name: ad,
        timezone: dilim,
        open_time: `${acilis}:00`,
        close_time: `${kapanis}:00`,
        closed_days: kapali,
      }),
    onSuccess: onKaydedildi,
  });

  return (
    <form
      onSubmit={(olay) => {
        olay.preventDefault();
        kaydet.mutate();
      }}
    >
      <h2 style={{ fontSize: 'var(--baslik-bolum)', marginTop: 0 }}>{tr.kurulum.markaBaslik}</h2>
      <p style={{ color: 'var(--renk-murekkep2)' }}>{tr.kurulum.markaAciklama}</p>

      <label className="alan-etiket">
        {tr.kurulum.markaAdi}
        <input
          value={ad}
          onChange={(olay) => setAd(olay.target.value)}
          required
          maxLength={120}
          className="alan"
        />
      </label>

      <label className="alan-etiket">
        {tr.kurulum.saatDilimi}
        <input value={dilim} onChange={(olay) => setDilim(olay.target.value)} className="alan" />
      </label>

      <div style={{ display: 'flex', gap: 'var(--bosluk-4)', flexWrap: 'wrap' }}>
        <label className="alan-etiket" style={{ flex: '1 1 160px' }}>
          {tr.kurulum.acilis}
          <input
            type="time"
            value={acilis}
            onChange={(olay) => setAcilis(olay.target.value)}
            className="alan"
          />
        </label>
        <label className="alan-etiket" style={{ flex: '1 1 160px' }}>
          {tr.kurulum.kapanis}
          <input
            type="time"
            value={kapanis}
            onChange={(olay) => setKapanis(olay.target.value)}
            className="alan"
          />
        </label>
      </div>

      <fieldset style={{ border: 'none', padding: 0, margin: 'var(--bosluk-4) 0' }}>
        <legend style={{ padding: 0, fontSize: 'var(--etiket)' }}>{tr.kurulum.kapaliGunler}</legend>
        <div style={{ display: 'flex', gap: 'var(--bosluk-2)', flexWrap: 'wrap' }}>
          {tr.kurulum.gunler.map((gun, sira) => (
            <label key={gun} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <input
                type="checkbox"
                checked={kapali.includes(sira)}
                onChange={(olay) =>
                  setKapali((onceki) =>
                    olay.target.checked ? [...onceki, sira] : onceki.filter((g) => g !== sira),
                  )
                }
              />
              {gun}
            </label>
          ))}
        </div>
      </fieldset>

      {kaydet.isError && (
        <p role="alert" style={{ color: 'var(--renk-kritik)' }}>
          {problemCoz(kaydet.error)?.title ?? tr.hata.aglaBaglanilamadi}
        </p>
      )}

      <Dugme type="submit" disabled={kaydet.isPending || !ad.trim()}>
        {kaydet.isPending ? tr.genel.yukleniyor : tr.kurulum.kaydet}
      </Dugme>
    </form>
  );
}

/**
 * Excel ile toplu yükleme adımı: şubeler (adım 2) ve personel (adım 5)
 * aynı akışı kullanıyor — indir, doldur, önizle, yükle.
 */
function YuklemeAdimi({
  tur,
  baslik,
  aciklama,
  sablonEtiketi,
  yukleEtiketi,
  sablon,
  onizleyici,
  yukleyici,
  onYuklendi,
}: {
  tur: Yukleme;
  baslik: string;
  aciklama: string;
  sablonEtiketi: string;
  yukleEtiketi: string;
  sablon: () => Promise<void>;
  onizleyici: (dosya: File) => Promise<YuklemeRaporu>;
  yukleyici: (dosya: File) => Promise<YuklemeRaporu>;
  onYuklendi: () => void;
}) {
  const [dosya, setDosya] = useState<File | null>(null);
  const [rapor, setRapor] = useState<YuklemeRaporu | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [yuklendi, setYuklendi] = useState(false);

  const onizle = useMutation({
    mutationFn: (secilen: File) => onizleyici(secilen),
    onSuccess: (sonuc) => {
      setRapor(sonuc);
      setHata(null);
    },
    onError: (sorun) => {
      setRapor(null);
      setHata(problemCoz(sorun)?.title ?? tr.hata.aglaBaglanilamadi);
    },
  });

  const yukle = useMutation({
    mutationFn: () => yukleyici(dosya as File),
    onSuccess: (sonuc) => {
      setRapor(sonuc);
      setYuklendi(true);
      onYuklendi();
    },
    onError: (sorun) => setHata(problemCoz(sorun)?.title ?? tr.hata.aglaBaglanilamadi),
  });

  return (
    <div>
      <h2 style={{ fontSize: 'var(--baslik-bolum)', marginTop: 0 }}>{baslik}</h2>
      <p style={{ color: 'var(--renk-murekkep2)' }}>{aciklama}</p>

      <Dugme gorunum="ikincil" type="button" onClick={() => void sablon()}>
        {sablonEtiketi}
      </Dugme>

      <label className="alan-etiket" style={{ marginTop: 'var(--bosluk-4)' }}>
        {tr.kurulum.dosyaSec}
        <input
          type="file"
          accept=".xlsx"
          onChange={(olay) => {
            const secilen = olay.target.files?.[0] ?? null;
            setDosya(secilen);
            setRapor(null);
            setYuklendi(false);
            setHata(null);
            if (secilen) onizle.mutate(secilen);
          }}
          style={{ marginTop: 'var(--bosluk-2)' }}
        />
      </label>

      {onizle.isPending && <p style={{ color: 'var(--renk-sessiz)' }}>{tr.genel.yukleniyor}</p>}

      {hata && (
        <div role="alert" style={{ color: 'var(--renk-kritik)', marginTop: 'var(--bosluk-4)' }}>
          <p>{hata}</p>
          {dosya && (
            <Dugme gorunum="ikincil" type="button" onClick={() => void hataRaporuIndir(dosya, tur)}>
              {tr.kurulum.hataRaporu}
            </Dugme>
          )}
        </div>
      )}

      {rapor && <RaporOzeti rapor={rapor} dosya={dosya} tur={tur} yuklendi={yuklendi} />}

      {rapor && !yuklendi && (
        <Dugme
          type="button"
          onClick={() => yukle.mutate()}
          disabled={yukle.isPending || rapor.accepted === 0}
        >
          {yukleEtiketi.replace('{n}', String(rapor.accepted))}
        </Dugme>
      )}
    </div>
  );
}

function RaporOzeti({
  rapor,
  dosya,
  tur,
  yuklendi,
}: {
  rapor: YuklemeRaporu;
  dosya: File | null;
  tur: Yukleme;
  yuklendi: boolean;
}) {
  return (
    <div style={{ marginTop: 'var(--bosluk-4)' }}>
      <div style={{ display: 'flex', gap: 'var(--bosluk-2)', flexWrap: 'wrap' }}>
        <Cip renk="nötr" metin={tr.kurulum.satirSayisi.replace('{n}', String(rapor.total))} />
        <Cip renk="marka" metin={tr.kurulum.kabul.replace('{n}', String(rapor.accepted))} />
        {rapor.error_rows > 0 && (
          <Cip
            renk="uyari"
            ikon="!"
            metin={tr.kurulum.hataliSatir.replace('{n}', String(rapor.error_rows))}
          />
        )}
        {yuklendi && (
          <Cip
            renk="marka"
            ikon="✓"
            metin={tr.kurulum.sonuc
              .replace('{yeni}', String(rapor.created))
              .replace('{guncel}', String(rapor.updated))}
          />
        )}
      </div>

      {rapor.errors.length > 0 && (
        <>
          <table
            style={{ width: '100%', borderCollapse: 'collapse', marginTop: 'var(--bosluk-3)' }}
          >
            <caption className="sr-only">{tr.kurulum.hataTablosu}</caption>
            <thead>
              <tr>
                <th>{tr.kurulum.satir}</th>
                <th>{tr.kurulum.sutun}</th>
                <th>{tr.kurulum.sorun}</th>
              </tr>
            </thead>
            <tbody>
              {rapor.errors.slice(0, 20).map((hata, sira) => (
                <tr key={`${hata.row}-${hata.field}-${sira}`}>
                  <td>{hata.row}</td>
                  <td>{hata.field}</td>
                  <td>{hata.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {dosya && (
            <Dugme gorunum="ikincil" type="button" onClick={() => void hataRaporuIndir(dosya, tur)}>
              {tr.kurulum.hataRaporu}
            </Dugme>
          )}
        </>
      )}
    </div>
  );
}

/** Adım 3 · kütüphaneden şablon seç (Ş-6). Seçim hesaba **kopyalanır**. */
function SablonAdimi({ onSecildi }: { onSecildi: () => void }) {
  const liste = useQuery({ queryKey: ['kurulum-kutuphane'], queryFn: kutuphane });
  // Sarmalayıcı kasıtlı: react-query mutationFn'e ikinci bir bağlam
  // argümanı geçiyor, doğrudan referans vermek çağrıyı bulandırıyor.
  const sec = useMutation({
    mutationFn: (key: string) => sablonKopyala(key),
    onSuccess: onSecildi,
  });

  return (
    <div>
      <h2 style={{ fontSize: 'var(--baslik-bolum)', marginTop: 0 }}>{tr.kurulum.sablonBaslik}</h2>
      <p style={{ color: 'var(--renk-murekkep2)' }}>{tr.kurulum.sablonAciklama}</p>

      {liste.isPending && <p style={{ color: 'var(--renk-sessiz)' }}>{tr.genel.yukleniyor}</p>}

      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {(liste.data ?? []).map((sablon) => (
          <li
            key={sablon.key}
            style={{
              border: '1px solid var(--renk-cizgi)',
              borderRadius: 'var(--kose-kart)',
              padding: 'var(--bosluk-4)',
              marginBottom: 'var(--bosluk-3)',
              background: 'var(--renk-yuzey2)',
            }}
          >
            <h3 style={{ margin: 0, fontSize: 'var(--govde)' }}>{sablon.name}</h3>
            <p style={{ color: 'var(--renk-murekkep2)', margin: 'var(--bosluk-2) 0' }}>
              {sablon.summary}
            </p>
            <div style={{ display: 'flex', gap: 'var(--bosluk-2)', flexWrap: 'wrap' }}>
              <Cip
                renk="nötr"
                metin={tr.kurulum.maddeSayisi.replace('{n}', String(sablon.item_count))}
              />
              <Cip
                renk="kritik"
                ikon="!"
                metin={tr.kurulum.kritikSayisi.replace('{n}', String(sablon.critical_count))}
              />
              <Cip renk="nötr" ikon="📷" metin={String(sablon.photo_count)} />
            </div>
            <p style={{ color: 'var(--renk-sessiz)', fontSize: 'var(--etiket)' }}>
              {sablon.window}
            </p>
            <Dugme type="button" onClick={() => sec.mutate(sablon.key)} disabled={sec.isPending}>
              {tr.kurulum.sablonuKullan}
            </Dugme>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Adım 4 · şube saatlerinden türetilmiş plan önerisi. */
function PlanAdimi({ onKaydedildi }: { onKaydedildi: () => void }) {
  const [ad, setAd] = useState('');
  const oneri = useQuery({ queryKey: ['kurulum-plan'], queryFn: planOnerisi });
  const kaydet = useMutation({
    mutationFn: () => planOlustur(ad || (oneri.data?.name ?? '')),
    onSuccess: onKaydedildi,
  });

  return (
    <div>
      <h2 style={{ fontSize: 'var(--baslik-bolum)', marginTop: 0 }}>{tr.kurulum.planBaslik}</h2>
      <p style={{ color: 'var(--renk-murekkep2)' }}>{tr.kurulum.planAciklama}</p>

      {oneri.isPending && <p style={{ color: 'var(--renk-sessiz)' }}>{tr.genel.yukleniyor}</p>}
      {oneri.isError && (
        <p role="alert" style={{ color: 'var(--renk-kritik)' }}>
          {problemCoz(oneri.error)?.title ?? tr.hata.aglaBaglanilamadi}
        </p>
      )}

      {oneri.data && (
        <>
          <label className="alan-etiket">
            {tr.kurulum.planAdi}
            <input
              value={ad || oneri.data.name}
              onChange={(olay) => setAd(olay.target.value)}
              className="alan"
            />
          </label>
          <ul style={{ paddingLeft: 'var(--bosluk-4)', color: 'var(--renk-murekkep2)' }}>
            <li>{oneri.data.window}</li>
            <li>{tr.kurulum.planSube.replace('{n}', String(oneri.data.branch_ids.length))}</li>
          </ul>
          <Dugme type="button" onClick={() => kaydet.mutate()} disabled={kaydet.isPending}>
            {tr.kurulum.planiOlustur}
          </Dugme>
        </>
      )}
    </div>
  );
}

function SonrakiAdimlar({
  adim,
  durum,
  onTamamla,
}: {
  adim: string;
  durum: KurulumDurumu;
  onTamamla: () => void;
}) {
  const yayin = useMutation({ mutationFn: kurulumYayinla, onSuccess: onTamamla });
  const bilgi = durum.steps.find((a) => a.step === adim);

  return (
    <div>
      <h2 style={{ fontSize: 'var(--baslik-bolum)', marginTop: 0 }}>{bilgi?.label}</h2>
      <p style={{ color: 'var(--renk-murekkep2)' }}>{bilgi?.detail}</p>

      {adim === 'review' ? (
        <>
          <ul style={{ paddingLeft: 'var(--bosluk-4)' }}>
            {durum.steps
              .filter((a) => a.step !== 'review')
              .map((a) => (
                <li key={a.step} style={{ marginBottom: 'var(--bosluk-2)' }}>
                  {a.done ? '✓' : '○'} {a.label} — {a.detail}
                </li>
              ))}
          </ul>
          {!durum.publishable && (
            <p role="alert" style={{ color: 'var(--renk-uyari)' }}>
              {tr.kurulum.yayinEngeli}
            </p>
          )}
          <Dugme
            type="button"
            onClick={() => yayin.mutate()}
            disabled={!durum.publishable || yayin.isPending}
          >
            {tr.kurulum.yayinla}
          </Dugme>

          {yayin.data && (
            <p style={{ marginTop: 'var(--bosluk-4)' }}>
              ✓ {tr.kurulum.yayinSonucu.replace('{n}', String(yayin.data.runs_ready))}
              {yayin.data.first_window
                ? ` · ${tr.kurulum.ilkPencere.replace(
                    '{t}',
                    new Date(yayin.data.first_window).toLocaleString('tr-TR'),
                  )}`
                : ''}
            </p>
          )}
        </>
      ) : (
        <p style={{ color: 'var(--renk-sessiz)' }}>{tr.kurulum.panelden}</p>
      )}
    </div>
  );
}
