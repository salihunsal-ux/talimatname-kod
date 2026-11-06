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
import { Hata, Yukleniyor } from '../../bilesenler/Durum';

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

  if (durum.isPending) return <Yukleniyor />;
  if (durum.isError || !durum.data)
    return <Hata hata={durum.error} metin={tr.hata.aglaBaglanilamadi} />;

  const veri = durum.data;
  const secili = acik ?? veri.current;
  const yenile = () => istemci.invalidateQueries({ queryKey: ['kurulum'] });

  return (
    <div className="dar-sayfa">
      <header className="sayfa-basligi">
        <div>
          <h1>{tr.kurulum.baslik}</h1>
          <p className="sayfa-basligi-alt">{tr.kurulum.aciklama}</p>
        </div>
      </header>

      <AdimCubugu durum={veri} secili={secili} onSec={setAcik} />

      <section className="kart">
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
    <ol className="sekme-serit">
      {durum.steps.map((adim, sira) => {
        const aktif = adim.step === secili;
        return (
          <li key={adim.step}>
            <Dugme
              gorunum="ikincil"
              boyut="kucuk"
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
      <header className="bolum-basligi">
        <h2>{tr.kurulum.markaBaslik}</h2>
        <p>{tr.kurulum.markaAciklama}</p>
      </header>

      <div className="yigin">
        <div className="alan-sirasi">
          <label className="alan-etiket">
            {tr.kurulum.markaAdi}
            <input
              value={ad}
              onChange={(olay) => setAd(olay.target.value)}
              required
              maxLength={120}
              className="alan alan--orta"
            />
          </label>
          <label className="alan-etiket">
            {tr.kurulum.saatDilimi}
            <input
              value={dilim}
              onChange={(olay) => setDilim(olay.target.value)}
              className="alan alan--orta"
            />
          </label>
        </div>

        <div className="alan-sirasi">
          <label className="alan-etiket">
            {tr.kurulum.acilis}
            <input
              type="time"
              value={acilis}
              onChange={(olay) => setAcilis(olay.target.value)}
              className="alan alan--saat"
            />
          </label>
          <label className="alan-etiket">
            {tr.kurulum.kapanis}
            <input
              type="time"
              value={kapanis}
              onChange={(olay) => setKapanis(olay.target.value)}
              className="alan alan--saat"
            />
          </label>
        </div>

        <fieldset className="alan-grubu">
          <legend>{tr.kurulum.kapaliGunler}</legend>
          <div className="alan-sirasi">
            {tr.kurulum.gunler.map((gun, sira) => (
              <label key={gun} className="secim-cipi">
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

        {kaydet.isError && <Hata hata={kaydet.error} />}

        <div className="eylemler">
          <Dugme type="submit" disabled={kaydet.isPending || !ad.trim()}>
            {kaydet.isPending ? tr.genel.yukleniyor : tr.kurulum.kaydet}
          </Dugme>
        </div>
      </div>
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
      <header className="bolum-basligi">
        <h2>{baslik}</h2>
        <p>{aciklama}</p>
      </header>

      <div className="yigin">
        <div className="eylemler">
          <Dugme gorunum="ikincil" type="button" onClick={() => void sablon()}>
            {sablonEtiketi}
          </Dugme>
        </div>

        <label className="alan-etiket">
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
          />
        </label>

        {onizle.isPending && <Yukleniyor />}

        {hata && (
          <div role="alert" className="bildiri bildiri--hata">
            <p>{hata}</p>
            {dosya && (
              <Dugme
                gorunum="ikincil"
                boyut="kucuk"
                type="button"
                onClick={() => void hataRaporuIndir(dosya, tur)}
              >
                {tr.kurulum.hataRaporu}
              </Dugme>
            )}
          </div>
        )}

        {rapor && <RaporOzeti rapor={rapor} dosya={dosya} tur={tur} yuklendi={yuklendi} />}

        {rapor && !yuklendi && (
          <div className="eylemler">
            <Dugme
              type="button"
              onClick={() => yukle.mutate()}
              disabled={yukle.isPending || rapor.accepted === 0}
            >
              {yukleEtiketi.replace('{n}', String(rapor.accepted))}
            </Dugme>
          </div>
        )}
      </div>
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
    <div className="yigin yigin--dar">
      <div className="cip-listesi">
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
          <div className="tablo-kaydirma">
            <table className="tablo">
              <caption className="sr-only">{tr.kurulum.hataTablosu}</caption>
              <thead>
                <tr>
                  <th className="sayisal">{tr.kurulum.satir}</th>
                  <th>{tr.kurulum.sutun}</th>
                  <th>{tr.kurulum.sorun}</th>
                </tr>
              </thead>
              <tbody>
                {rapor.errors.slice(0, 20).map((hata, sira) => (
                  <tr key={`${hata.row}-${hata.field}-${sira}`}>
                    <td className="sayisal">{hata.row}</td>
                    <td>{hata.field}</td>
                    <td>{hata.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {dosya && (
            <div className="eylemler">
              <Dugme
                gorunum="ikincil"
                type="button"
                onClick={() => void hataRaporuIndir(dosya, tur)}
              >
                {tr.kurulum.hataRaporu}
              </Dugme>
            </div>
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
      <header className="bolum-basligi">
        <h2>{tr.kurulum.sablonBaslik}</h2>
        <p>{tr.kurulum.sablonAciklama}</p>
      </header>

      {liste.isPending && <Yukleniyor />}

      <ul className="liste-yigin">
        {(liste.data ?? []).map((sablon) => (
          <li key={sablon.key} className="kart">
            <div className="yigin yigin--dar">
              <div>
                <h3 className="kart-serit-ad">{sablon.name}</h3>
                <p className="ikincil-metin">{sablon.summary}</p>
              </div>
              <div className="cip-listesi">
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
              <p className="meta">{sablon.window}</p>
              <div className="eylemler">
                <Dugme
                  type="button"
                  onClick={() => sec.mutate(sablon.key)}
                  disabled={sec.isPending}
                >
                  {tr.kurulum.sablonuKullan}
                </Dugme>
              </div>
            </div>
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
      <header className="bolum-basligi">
        <h2>{tr.kurulum.planBaslik}</h2>
        <p>{tr.kurulum.planAciklama}</p>
      </header>

      {oneri.isPending && <Yukleniyor />}
      {oneri.isError && <Hata hata={oneri.error} />}

      {oneri.data && (
        <div className="yigin">
          <label className="alan-etiket">
            {tr.kurulum.planAdi}
            <input
              value={ad || oneri.data.name}
              onChange={(olay) => setAd(olay.target.value)}
              className="alan alan--orta"
            />
          </label>
          <ul className="madde-listesi">
            <li>{oneri.data.window}</li>
            <li>{tr.kurulum.planSube.replace('{n}', String(oneri.data.branch_ids.length))}</li>
          </ul>
          <div className="eylemler">
            <Dugme type="button" onClick={() => kaydet.mutate()} disabled={kaydet.isPending}>
              {tr.kurulum.planiOlustur}
            </Dugme>
          </div>
        </div>
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
      <header className="bolum-basligi">
        <h2>{bilgi?.label}</h2>
        <p>{bilgi?.detail}</p>
      </header>

      {adim === 'review' ? (
        <div className="yigin">
          <ul className="madde-listesi">
            {durum.steps
              .filter((a) => a.step !== 'review')
              .map((a) => (
                <li key={a.step}>
                  {a.done ? '✓' : '○'} {a.label} — {a.detail}
                </li>
              ))}
          </ul>
          {!durum.publishable && (
            <p role="alert" className="bildiri bildiri--uyari">
              {tr.kurulum.yayinEngeli}
            </p>
          )}
          <div className="eylemler">
            <Dugme
              type="button"
              onClick={() => yayin.mutate()}
              disabled={!durum.publishable || yayin.isPending}
            >
              {tr.kurulum.yayinla}
            </Dugme>
          </div>

          {yayin.data && (
            <p role="status" className="bildiri bildiri--saglam">
              ✓ {tr.kurulum.yayinSonucu.replace('{n}', String(yayin.data.runs_ready))}
              {yayin.data.first_window
                ? ` · ${tr.kurulum.ilkPencere.replace(
                    '{t}',
                    new Date(yayin.data.first_window).toLocaleString('tr-TR'),
                  )}`
                : ''}
            </p>
          )}
        </div>
      ) : (
        <p className="durum-metni">{tr.kurulum.panelden}</p>
      )}
    </div>
  );
}
