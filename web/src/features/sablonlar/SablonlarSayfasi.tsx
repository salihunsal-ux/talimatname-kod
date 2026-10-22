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
import { tr } from '../../i18n/tr';

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
  const [seciliSurum, setSeciliSurum] = useState<string | null>(null);

  const sablonlar = useQuery({ queryKey: ['sablonlar'], queryFn: sablonListesi });

  useEffect(() => {
    if (seciliSurum || !sablonlar.data?.length) return;
    const ilk = sablonlar.data[0]?.versions[0];
    if (ilk) setSeciliSurum(ilk.id);
  }, [sablonlar.data, seciliSurum]);

  return (
    <div style={{ display: 'flex', gap: 'var(--bosluk-6)', flexWrap: 'wrap' }}>
      <div style={{ flex: '0 1 320px', minWidth: 260 }}>
        <h1 style={{ fontSize: 'var(--baslik-bolum)', margin: '0 0 var(--bosluk-3)' }}>
          {tr.sablon.baslik}
        </h1>

        {sablonlar.isPending && (
          <p style={{ color: 'var(--renk-sessiz)' }}>{tr.genel.yukleniyor}</p>
        )}
        {sablonlar.isError && (
          <p role="alert" style={{ color: 'var(--renk-kritik)' }}>
            {tr.hata.aglaBaglanilamadi}
          </p>
        )}

        {sablonlar.data?.map((sablon) => (
          <section key={sablon.id} style={{ marginBottom: 'var(--bosluk-4)' }}>
            <h2 style={{ fontSize: 'var(--govde)', margin: '0 0 var(--bosluk-2)' }}>
              {sablon.name}
            </h2>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
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

        <SablonEkleFormu onOlusturuldu={(detay) => setSeciliSurum(detay.id)} />
      </div>

      <div style={{ flex: '1 1 420px', minWidth: 320 }}>
        {seciliSurum ? <SurumEditoru id={seciliSurum} onSurumDegisti={setSeciliSurum} /> : null}
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
    <button
      type="button"
      onClick={onSec}
      aria-current={secili}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--bosluk-2)',
        width: '100%',
        padding: 'var(--bosluk-2) var(--bosluk-3)',
        marginBottom: 'var(--bosluk-1)',
        textAlign: 'left',
        borderRadius: 'var(--kose-dugme)',
        border: '1px solid',
        borderColor: secili ? 'var(--renk-marka)' : 'var(--renk-cizgi)',
        background: secili ? 'var(--renk-marka-acik)' : 'var(--renk-yuzey)',
        color: 'var(--renk-murekkep)',
        cursor: 'pointer',
      }}
    >
      <span style={{ flex: 1 }}>
        {tr.sablon.surum} {surum.version_no}
      </span>
      <Cip renk={cip.renk} ikon={cip.ikon} metin={cip.metin} />
    </button>
  );
}

function SurumEditoru({
  id,
  onSurumDegisti,
}: {
  id: string;
  onSurumDegisti: (id: string) => void;
}) {
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

  if (detay.isPending) return <p style={{ color: 'var(--renk-sessiz)' }}>{tr.genel.yukleniyor}</p>;
  if (detay.isError || !detay.data)
    return (
      <p role="alert" style={{ color: 'var(--renk-kritik)' }}>
        {tr.hata.genel}
      </p>
    );

  const surum = detay.data;
  const duzenlenebilir = surum.status === 'draft';
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
    <article
      style={{
        background: 'var(--renk-yuzey)',
        border: '1px solid var(--renk-cizgi)',
        borderRadius: 'var(--kose-kart)',
        padding: 'var(--bosluk-4)',
      }}
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 'var(--bosluk-3)',
          flexWrap: 'wrap',
        }}
      >
        <h2 style={{ fontSize: 'var(--baslik-bolum)', margin: 0 }}>{surum.template_name}</h2>
        <Cip {...DURUM_CIPI[surum.status]} />
        <span style={{ color: 'var(--renk-sessiz)', fontSize: 'var(--meta)' }}>
          {tr.sablon.surum} {surum.version_no} · {surum.scored_item_count} {tr.sablon.puanlanan} ·{' '}
          {surum.critical_item_count} {tr.sablon.kritik} · {surum.photo_item_count}{' '}
          {tr.sablon.fotograf}
        </span>
      </header>

      {!duzenlenebilir && (
        <p
          style={{
            background: 'var(--renk-yuzey2)',
            borderRadius: 'var(--kose-dugme)',
            padding: 'var(--bosluk-2) var(--bosluk-3)',
            color: 'var(--renk-murekkep2)',
            fontSize: 'var(--etiket)',
          }}
        >
          {tr.sablon.yayinDegismez}{' '}
          <button type="button" onClick={() => turet.mutate()} style={kucukDugme}>
            {tr.sablon.yeniTaslak}
          </button>
        </p>
      )}

      {bolumler.map((bolum, bolumSira) => (
        <section key={bolum.id ?? bolumSira} style={{ marginTop: 'var(--bosluk-4)' }}>
          <h3
            style={{
              fontSize: 'var(--etiket)',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: 'var(--renk-sessiz)',
            }}
          >
            {bolum.title}
          </h3>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
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
        <div
          role="status"
          style={{
            marginTop: 'var(--bosluk-4)',
            background: 'var(--renk-uyari-acik)',
            color: 'var(--renk-murekkep)',
            borderRadius: 'var(--kose-dugme)',
            padding: 'var(--bosluk-3)',
            fontSize: 'var(--etiket)',
          }}
        >
          <strong>{tr.sablon.yayinEngelleri}</strong>
          <ul style={{ margin: 'var(--bosluk-2) 0 0', paddingLeft: 'var(--bosluk-4)' }}>
            {surum.publish_issues.map((sorun, sira) => (
              <li key={`${sorun.where}-${sira}`}>{sorun.message}</li>
            ))}
          </ul>
        </div>
      )}

      {duzenlenebilir && (
        <div
          style={{
            display: 'flex',
            gap: 'var(--bosluk-2)',
            marginTop: 'var(--bosluk-4)',
            flexWrap: 'wrap',
          }}
        >
          <button
            type="button"
            disabled={taslak === null || kaydet.isPending}
            onClick={() => taslak && kaydet.mutate(taslak)}
            style={{ ...anaDugme, opacity: taslak === null ? 0.5 : 1 }}
          >
            {tr.sablon.kaydet}
          </button>
          <button
            type="button"
            disabled={surum.publish_issues.length > 0 || taslak !== null || yayinla.isPending}
            onClick={() => yayinla.mutate()}
            title={taslak !== null ? tr.sablon.oncekaydet : undefined}
            style={{
              ...anaDugme,
              background: 'var(--renk-yuzey2)',
              color: 'var(--renk-murekkep)',
              borderColor: 'var(--renk-cizgi)',
              opacity: surum.publish_issues.length > 0 || taslak !== null ? 0.5 : 1,
            }}
          >
            {tr.sablon.yayinla}
          </button>
          {taslak !== null && (
            <span
              style={{ alignSelf: 'center', color: 'var(--renk-uyari)', fontSize: 'var(--etiket)' }}
            >
              {tr.sablon.kaydedilmemis}
            </span>
          )}
        </div>
      )}

      {yayinProblemi && (
        <p role="alert" style={{ color: 'var(--renk-kritik)' }}>
          {yayinProblemi.title}
        </p>
      )}
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
    <li
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--bosluk-2)',
        flexWrap: 'wrap',
        padding: 'var(--bosluk-2) 0',
        borderTop: '1px solid var(--renk-cizgi)',
      }}
    >
      <span style={{ flex: '1 1 220px' }}>{madde.title}</span>
      <Cip renk="nötr" metin={tur} />
      {aralikli && (
        <span
          style={{
            color: 'var(--renk-sessiz)',
            fontSize: 'var(--meta)',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {madde.min_value ?? '?'}–{madde.max_value ?? '?'} {madde.unit ?? ''}
        </span>
      )}
      {madde.photo_required && <Cip renk="nötr" ikon="📷" metin={tr.sablon.fotografZorunlu} />}
      {madde.critical && <Cip renk="kritik" ikon="!" metin={tr.sablon.kritik} />}
      {duzenlenebilir && (
        <>
          <label style={{ fontSize: 'var(--meta)', display: 'flex', gap: 4, alignItems: 'center' }}>
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
          <button
            type="button"
            onClick={onSil}
            style={kucukDugme}
            aria-label={`${madde.title} ${tr.sablon.sil}`}
          >
            {tr.sablon.sil}
          </button>
        </>
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
      style={{
        display: 'flex',
        gap: 'var(--bosluk-2)',
        flexWrap: 'wrap',
        marginTop: 'var(--bosluk-2)',
      }}
    >
      <input
        value={baslik}
        onChange={(o) => setBaslik(o.target.value)}
        placeholder={tr.sablon.maddeBasligi}
        aria-label={tr.sablon.maddeBasligi}
        style={{ ...alanBicimi, flex: '1 1 200px' }}
      />
      <select
        value={tur}
        onChange={(o) => setTur(o.target.value as MaddeTuru)}
        aria-label={tr.sablon.maddeTuru}
        style={alanBicimi}
      >
        {TURLER.map((t) => (
          <option key={t.deger} value={t.deger}>
            {t.etiket}
          </option>
        ))}
      </select>
      <button type="submit" style={kucukDugme}>
        {tr.sablon.maddeEkle}
      </button>
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
      style={{ display: 'flex', gap: 'var(--bosluk-2)', marginTop: 'var(--bosluk-4)' }}
    >
      <input
        value={baslik}
        onChange={(o) => setBaslik(o.target.value)}
        placeholder={tr.sablon.bolumBasligi}
        aria-label={tr.sablon.bolumBasligi}
        style={{ ...alanBicimi, flex: '1 1 200px' }}
      />
      <button type="submit" style={kucukDugme}>
        {tr.sablon.bolumEkle}
      </button>
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
      style={{
        display: 'flex',
        gap: 'var(--bosluk-2)',
        marginTop: 'var(--bosluk-4)',
        paddingTop: 'var(--bosluk-4)',
        borderTop: '1px solid var(--renk-cizgi)',
      }}
    >
      <input
        value={ad}
        onChange={(o) => setAd(o.target.value)}
        required
        placeholder={tr.sablon.sablonAdi}
        aria-label={tr.sablon.sablonAdi}
        style={{ ...alanBicimi, flex: 1 }}
      />
      <button type="submit" style={anaDugme}>
        {tr.sablon.sablonEkle}
      </button>
    </form>
  );
}

const alanBicimi = {
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
  borderRadius: 'var(--kose-dugme)',
  border: '1px solid var(--renk-marka)',
  background: 'var(--renk-marka)',
  color: '#fff',
  cursor: 'pointer',
} as const;
