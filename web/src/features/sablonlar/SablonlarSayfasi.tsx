import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { problemCoz } from '../../api/client';
import {
  sablonListesi,
  sablonOlustur,
  surumDetayi,
  surumYayinla,
  taslakKaydet,
  yeniTaslak,
  type BolumGirdisi,
  type MaddeGirdisi,
  type MaddeTuru,
  type SurumDetay,
  type SurumOzet,
} from '../../api/sablonlar';
import { Cip } from '../../bilesenler/Cip';
import { useYonetici } from '../../api/yetki';
import { tr } from '../../i18n/tr';
import { Dugme } from '../../bilesenler/Dugme';

const TURLER: { deger: MaddeTuru; etiket: string }[] = [
  { deger: 'confirm', etiket: 'Onay' },
  { deger: 'choice', etiket: 'Çoktan seçmeli' },
  { deger: 'number', etiket: 'Sayı' },
  { deger: 'temperature', etiket: 'Sıcaklık' },
  { deger: 'text', etiket: 'Metin' },
  { deger: 'photo', etiket: 'Fotoğraf' },
  { deger: 'instruction', etiket: 'Talimat' },
];

const DURUM_CIPI = {
  published: { renk: 'marka' as const, ikon: '✓', metin: tr.sablon.yayinda },
  draft: { renk: 'uyari' as const, ikon: '◐', metin: tr.sablon.taslak },
  archived: { renk: 'pasif' as const, ikon: '–', metin: tr.sablon.arsiv },
};

/**
 * SCR-W-04/05 · Şablonlar ve basit editör. v1 kapsamı: 6 madde türü +
 * talimat, üç ayar (zorunlu · fotoğraf · kritik), sıcaklık aralığı.
 * Koşul editörü ve ağırlık v1.1'de (ADR-0008).
 */
export function SablonlarSayfasi() {
  const yonetici = useYonetici();
  const [seciliSurum, setSeciliSurum] = useState<string | null>(null);

  const sablonlar = useQuery({ queryKey: ['sablonlar'], queryFn: sablonListesi });

  useEffect(() => {
    if (seciliSurum || !sablonlar.data?.length) return;
    const ilk = sablonlar.data[0]?.versions[0];
    if (ilk) setSeciliSurum(ilk.id);
  }, [sablonlar.data, seciliSurum]);

  const bos = sablonlar.data?.length === 0;

  return (
    <div>
      <header className="sayfa-basligi">
        <div>
          <h1>{tr.sablon.baslik}</h1>
          <p className="sayfa-basligi-alt">{tr.sablon.altBaslik}</p>
        </div>
      </header>

      {sablonlar.isPending && <p className="meta">{tr.genel.yukleniyor}</p>}
      {sablonlar.isError && (
        <p role="alert" className="bildiri bildiri--hata">
          {tr.hata.aglaBaglanilamadi}
        </p>
      )}

      <div className="liste-detay">
        <div className="liste-detay-kenar">
          {bos && <p className="bos-durum">{tr.sablon.sablonYok}</p>}

          {sablonlar.data?.map((sablon) => (
            <section key={sablon.id}>
              <h2 className="bolum-etiketi">{sablon.name}</h2>
              <ul className="liste-yigin">
                {sablon.versions.map((surum) => (
                  <li key={surum.id}>
                    <SurumDugmesi
                      surum={surum}
                      secili={seciliSurum === surum.id}
                      onSec={() => setSeciliSurum(surum.id)}
                    />
                  </li>
                ))}
              </ul>
            </section>
          ))}

          {yonetici && <SablonEkleFormu onOlusturuldu={(detay) => setSeciliSurum(detay.id)} />}
        </div>

        <div>
          {seciliSurum ? (
            <SurumEditoru id={seciliSurum} onSurumDegisti={setSeciliSurum} />
          ) : (
            /* Sağ sütun boş bırakılmıyor: ne yapılacağını söylüyor. */
            !bos && <p className="bos-durum">{tr.sablon.secimYok}</p>
          )}
        </div>
      </div>
    </div>
  );
}

function SurumDugmesi({
  surum,
  secili,
  onSec,
}: {
  surum: SurumOzet;
  secili: boolean;
  onSec: () => void;
}) {
  const cip = DURUM_CIPI[surum.status];
  return (
    <Dugme gorunum="ikincil" tam type="button" onClick={onSec} aria-current={secili}>
      <span className="dugme-ad">
        {tr.sablon.surum} {surum.version_no}
      </span>
      <Cip renk={cip.renk} ikon={cip.ikon} metin={cip.metin} />
    </Dugme>
  );
}

function SurumEditoru({
  id,
  onSurumDegisti,
}: {
  id: string;
  onSurumDegisti: (id: string) => void;
}) {
  const yonetici = useYonetici();
  const kuyruk = useQueryClient();
  const detay = useQuery({ queryKey: ['surum', id], queryFn: () => surumDetayi(id) });
  const [taslak, setTaslak] = useState<BolumGirdisi[] | null>(null);

  useEffect(() => {
    setTaslak(null);
  }, [id]);

  const tazele = async () => {
    await kuyruk.invalidateQueries({ queryKey: ['sablonlar'] });
    await kuyruk.invalidateQueries({ queryKey: ['surum'] });
  };

  const kaydet = useMutation({
    mutationFn: (bolumler: BolumGirdisi[]) =>
      taslakKaydet(id, { sections: bolumler, camera_only: detay.data?.camera_only ?? true }),
    onSuccess: async () => {
      setTaslak(null);
      await tazele();
    },
  });
  const yayinla = useMutation({ mutationFn: () => surumYayinla(id), onSuccess: tazele });
  const turet = useMutation({
    mutationFn: () => yeniTaslak(detay.data!.template_id),
    onSuccess: async (yeni) => {
      await tazele();
      onSurumDegisti(yeni.id);
    },
  });

  if (detay.isPending) return <p className="meta">{tr.genel.yukleniyor}</p>;
  if (detay.isError || !detay.data)
    return (
      <p role="alert" className="bildiri bildiri--hata">
        {tr.hata.genel}
      </p>
    );

  const surum = detay.data;
  // Taslak olması yetmiyor: yazma yetkisi de gerek (ST-005).
  const duzenlenebilir = surum.status === 'draft' && yonetici;
  const bolumler: BolumGirdisi[] =
    taslak ??
    surum.sections.map((bolum) => ({
      id: bolum.id,
      title: bolum.title,
      items: bolum.items.map(
        ({
          id: maddeId,
          type,
          title,
          required,
          photo_required,
          critical,
          options,
          min_value,
          max_value,
          unit,
          hint,
        }) => ({
          id: maddeId,
          type,
          title,
          required,
          photo_required,
          critical,
          options,
          min_value,
          max_value,
          unit,
          hint,
        }),
      ),
    }));

  const degistir = (yeni: BolumGirdisi[]) => setTaslak(yeni);
  const yayinProblemi = problemCoz(yayinla.error);

  return (
    <article className="kart">
      {/* Başlıkta şablonun adı, altında sayılar: sürüm numarası ve madde
          dökümü kartı tanıtmıyor, başlığın yanında gürültü yapıyordu. */}
      <header className="kart-serit">
        <div className="kart-serit-ad">
          <h2 className="baslik-bolum">{surum.template_name}</h2>
          <p className="meta">
            {tr.sablon.surum} {surum.version_no} · {surum.scored_item_count} {tr.sablon.puanlanan} ·{' '}
            {surum.critical_item_count} {tr.sablon.kritik} · {surum.photo_item_count}{' '}
            {tr.sablon.fotograf}
          </p>
        </div>
        <Cip {...DURUM_CIPI[surum.status]} />
      </header>

      <div className="yigin">
        {!duzenlenebilir && (
          <div className="bildiri kart-serit">
            <span className="kart-serit-ad">{tr.sablon.yayinDegismez}</span>
            {yonetici && (
              <Dugme gorunum="ikincil" boyut="kucuk" type="button" onClick={() => turet.mutate()}>
                {tr.sablon.yeniTaslak}
              </Dugme>
            )}
          </div>
        )}

        {bolumler.length === 0 && duzenlenebilir && (
          <p className="bos-durum">{tr.sablon.bolumYok}</p>
        )}

        {bolumler.map((bolum, bolumSira) => (
          <section key={bolum.id ?? bolumSira} className="yigin yigin--dar">
            <h3 className="bolum-etiketi">
              {bolum.title}
              <span className="baslik-eki"> · {tr.sablon.maddeler(bolum.items?.length ?? 0)}</span>
            </h3>
            {(bolum.items ?? []).length === 0 && <p className="meta">{tr.sablon.maddeYok}</p>}
            <ul className="sade-liste">
              {(bolum.items ?? []).map((madde, maddeSira) => (
                <MaddeSatiri
                  key={madde.id ?? `${bolumSira}-${maddeSira}`}
                  madde={madde}
                  duzenlenebilir={duzenlenebilir}
                  onDegis={(yeni) => {
                    const kopya = bolumler.map((b) => ({ ...b, items: [...(b.items ?? [])] }));
                    kopya[bolumSira].items[maddeSira] = yeni;
                    degistir(kopya);
                  }}
                  onSil={() => {
                    const kopya = bolumler.map((b) => ({ ...b, items: [...(b.items ?? [])] }));
                    kopya[bolumSira].items.splice(maddeSira, 1);
                    degistir(kopya);
                  }}
                />
              ))}
            </ul>
            {duzenlenebilir && (
              <MaddeEkle
                onEkle={(yeni) => {
                  const kopya = bolumler.map((b) => ({ ...b, items: [...(b.items ?? [])] }));
                  kopya[bolumSira].items.push(yeni);
                  degistir(kopya);
                }}
              />
            )}
          </section>
        ))}

        {duzenlenebilir && (
          <BolumEkle onEkle={(baslik) => degistir([...bolumler, { title: baslik, items: [] }])} />
        )}

        {surum.publish_issues.length > 0 && (
          <div role="status" className="bildiri bildiri--uyari">
            <strong>{tr.sablon.yayinEngelleri}</strong>
            <ul className="madde-listesi">
              {surum.publish_issues.map((sorun, sira) => (
                <li key={`${sorun.where}-${sira}`}>{sorun.message}</li>
              ))}
            </ul>
          </div>
        )}

        {duzenlenebilir && (
          <div className="eylemler">
            <Dugme
              type="button"
              disabled={taslak === null || kaydet.isPending}
              onClick={() => taslak && kaydet.mutate(taslak)}
            >
              {tr.sablon.kaydet}
            </Dugme>
            {/* Yayınla ikincil: geri alınamaz ama ekranın asıl işi değil.
              Birincil olan, yapılan çalışmayı kaybetmeyen kaydetme. */}
            <Dugme
              gorunum="ikincil"
              type="button"
              disabled={surum.publish_issues.length > 0 || taslak !== null || yayinla.isPending}
              onClick={() => yayinla.mutate()}
              title={taslak !== null ? tr.sablon.oncekaydet : undefined}
            >
              {tr.sablon.yayinla}
            </Dugme>
            {taslak !== null && <span className="uyari-metni">{tr.sablon.kaydedilmemis}</span>}
          </div>
        )}

        {yayinProblemi && (
          <p role="alert" className="bildiri bildiri--hata">
            {yayinProblemi.title}
          </p>
        )}
      </div>
    </article>
  );
}

function MaddeSatiri({
  madde,
  duzenlenebilir,
  onDegis,
  onSil,
}: {
  madde: MaddeGirdisi;
  duzenlenebilir: boolean;
  onDegis: (yeni: MaddeGirdisi) => void;
  onSil: () => void;
}) {
  const tur = TURLER.find((t) => t.deger === madde.type)?.etiket ?? madde.type;
  const aralikli = madde.type === 'temperature' || madde.type === 'number';

  return (
    <li className="madde-satiri">
      <span className="madde-satiri-ad">{madde.title}</span>
      <Cip renk="nötr" metin={tur} />
      {aralikli && (
        <span className="meta sayisal">
          {madde.min_value ?? '?'}–{madde.max_value ?? '?'} {madde.unit ?? ''}
        </span>
      )}
      {madde.photo_required && <Cip renk="nötr" ikon="📷" metin={tr.sablon.fotografZorunlu} />}
      {madde.critical && <Cip renk="kritik" ikon="!" metin={tr.sablon.kritik} />}
      {duzenlenebilir && (
        /* Eylemler sağa toplanıyor: soldakiler maddeyi anlatıyor,
           bunlar maddeyi değiştiriyor; araya karışınca satırda ikisi
           ayırt edilemiyordu. */
        <span className="madde-satiri-eylem">
          <label className="secim-cipi">
            <input
              type="checkbox"
              checked={madde.critical ?? false}
              onChange={(o) =>
                onDegis({
                  ...madde,
                  critical: o.target.checked,
                  required: o.target.checked ? true : madde.required,
                })
              }
              aria-label={`${madde.title} ${tr.sablon.kritik}`}
            />
            {tr.sablon.kritik}
          </label>
          <Dugme
            type="button"
            onClick={onSil}
            gorunum="sessiz"
            boyut="kucuk"
            aria-label={`${madde.title} ${tr.sablon.sil}`}
          >
            {tr.sablon.sil}
          </Dugme>
        </span>
      )}
    </li>
  );
}

function MaddeEkle({ onEkle }: { onEkle: (madde: MaddeGirdisi) => void }) {
  const [baslik, setBaslik] = useState('');
  const [tur, setTur] = useState<MaddeTuru>('confirm');

  return (
    <form
      onSubmit={(olay) => {
        olay.preventDefault();
        if (!baslik.trim()) return;
        const temel: MaddeGirdisi = { type: tur, title: baslik, required: true };
        onEkle(
          tur === 'choice'
            ? {
                ...temel,
                options: [
                  { label: 'Evet', passing: true },
                  { label: 'Hayır', passing: false },
                ],
              }
            : tur === 'temperature'
              ? { ...temel, min_value: 0, max_value: 4, unit: '°C' }
              : temel,
        );
        setBaslik('');
      }}
      className="alan-sirasi"
    >
      <label className="alan-etiket alan-etiket--genis">
        {tr.sablon.maddeBasligi}
        <input
          value={baslik}
          onChange={(o) => setBaslik(o.target.value)}
          aria-label={tr.sablon.maddeBasligi}
          className="alan"
        />
      </label>
      <label className="alan-etiket">
        {tr.sablon.maddeTuru}
        <select
          value={tur}
          onChange={(o) => setTur(o.target.value as MaddeTuru)}
          aria-label={tr.sablon.maddeTuru}
          className="alan"
        >
          {TURLER.map((t) => (
            <option key={t.deger} value={t.deger}>
              {t.etiket}
            </option>
          ))}
        </select>
      </label>
      <Dugme type="submit" gorunum="ikincil">
        {tr.sablon.maddeEkle}
      </Dugme>
    </form>
  );
}

function BolumEkle({ onEkle }: { onEkle: (baslik: string) => void }) {
  const [baslik, setBaslik] = useState('');
  return (
    <form
      onSubmit={(olay) => {
        olay.preventDefault();
        if (!baslik.trim()) return;
        onEkle(baslik);
        setBaslik('');
      }}
      className="alan-sirasi alan-grubu--ayri"
    >
      <label className="alan-etiket alan-etiket--genis">
        {tr.sablon.bolumBasligi}
        <input
          value={baslik}
          onChange={(o) => setBaslik(o.target.value)}
          aria-label={tr.sablon.bolumBasligi}
          className="alan"
        />
      </label>
      <Dugme type="submit" gorunum="ikincil">
        {tr.sablon.bolumEkle}
      </Dugme>
    </form>
  );
}

function SablonEkleFormu({ onOlusturuldu }: { onOlusturuldu: (detay: SurumDetay) => void }) {
  const kuyruk = useQueryClient();
  const [ad, setAd] = useState('');
  const olustur = useMutation({
    mutationFn: () => sablonOlustur(ad),
    onSuccess: async (detay) => {
      setAd('');
      await kuyruk.invalidateQueries({ queryKey: ['sablonlar'] });
      onOlusturuldu(detay);
    },
  });

  return (
    <form
      onSubmit={(olay) => {
        olay.preventDefault();
        olustur.mutate();
      }}
    >
      <fieldset className="alan-grubu">
        <legend>{tr.sablon.yeniSablon}</legend>
        <div className="alan-sirasi">
          <label className="alan-etiket alan-etiket--genis">
            {tr.sablon.sablonAdi}
            <input
              value={ad}
              onChange={(o) => setAd(o.target.value)}
              required
              aria-label={tr.sablon.sablonAdi}
              className="alan"
            />
          </label>
          <Dugme type="submit">{tr.sablon.sablonEkle}</Dugme>
        </div>
      </fieldset>
    </form>
  );
}
