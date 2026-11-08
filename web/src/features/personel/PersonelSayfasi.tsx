import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { problemCoz } from '../../api/client';
import {
  personelDavet,
  personelDuzelt,
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
import { Dugme } from '../../bilesenler/Dugme';
import { Hata } from '../../bilesenler/Durum';
import { IskeletTablo } from '../../bilesenler/Iskelet';

const ROLLER: { deger: Rol; etiket: string; kapsam: 'yok' | 'bolge' | 'sube' }[] = [
  { deger: 'admin', etiket: 'Yönetici', kapsam: 'yok' },
  { deger: 'region_manager', etiket: 'Bölge müdürü', kapsam: 'bolge' },
  // Denetçi de bölge kapsamlı: şubeye gider ama şubeye bağlı değil.
  { deger: 'auditor', etiket: 'Denetçi', kapsam: 'bolge' },
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
      <header className="sayfa-basligi">
        <div>
          <h1>{tr.personel.baslik}</h1>
          <p className="sayfa-basligi-alt">{tr.personel.altBaslik}</p>
        </div>
      </header>

      <div className="suzgec-serit">
        <label className="alan-etiket">
          {tr.personel.sube}
          <select
            value={subeSuzgeci}
            onChange={(o) => setSubeSuzgeci(o.target.value)}
            className="alan"
          >
            <option value="">{tr.personel.hepsi}</option>
            {duzSubeler.map((sube) => (
              <option key={sube.id} value={sube.id}>
                {sube.name} ({sube.code})
              </option>
            ))}
          </select>
        </label>

        <label className="alan-etiket">
          {tr.personel.rol}
          <select
            value={rolSuzgeci}
            onChange={(o) => setRolSuzgeci(o.target.value)}
            className="alan"
          >
            <option value="">{tr.personel.hepsi}</option>
            {ROLLER.map((rol) => (
              <option key={rol.deger} value={rol.deger}>
                {rol.etiket}
              </option>
            ))}
          </select>
        </label>

        <label className="onay-etiketi">
          <input
            type="checkbox"
            checked={pasifDahil}
            onChange={(o) => setPasifDahil(o.target.checked)}
          />
          {tr.personel.pasifleriGoster}
        </label>
      </div>

      {personel.isPending && <IskeletTablo sutunlar={4} />}
      {personel.isError && <Hata hata={personel.error} metin={tr.hata.aglaBaglanilamadi} />}

      {personel.data && personel.data.length === 0 && (
        <p className="bos-durum">{tr.personel.bos}</p>
      )}

      {personel.data && personel.data.length > 0 && (
        <div className="tablo-kaydirma">
          <table className="tablo">
            <thead>
              <tr>
                <th>{tr.personel.ad}</th>
                <th>{tr.personel.rolKapsam}</th>
                <th>{tr.personel.telefon}</th>
                <th className="eylem">{tr.personel.islem}</th>
              </tr>
            </thead>
            <tbody>
              {personel.data.map((kisi) => (
                <PersonelSatiri
                  key={kisi.id}
                  kisi={kisi}
                  kapsamAdi={kapsamAdiCozucu(kapsamAdlari)}
                />
              ))}
            </tbody>
          </table>
        </div>
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
  // Ad düzeltmesi satırın içinde: yanlış yazılmış bir isim cevap
  // satırlarında ve imzalı raporlarda görünüyor, düzeltmek için toplu
  // içe aktarmaya dönmek gerekmemeli.
  const [duzenlenen, setDuzenlenen] = useState<string | null>(null);

  const tazele = async () => {
    await kuyruk.invalidateQueries({ queryKey: ['personel'] });
  };
  const pasiflestir = useMutation({
    mutationFn: () => personelPasiflestir(kisi.id),
    onSuccess: tazele,
  });
  const maskele = useMutation({ mutationFn: () => personelMaskele(kisi.id), onSuccess: tazele });
  const duzelt = useMutation({
    mutationFn: (ad: string) => personelDuzelt(kisi.id, { full_name: ad }),
    onSuccess: async () => {
      setDuzenlenen(null);
      await tazele();
    },
  });
  const duzeltmeProblemi = problemCoz(duzelt.error);
  const yeniAd = (duzenlenen ?? '').trim();

  return (
    <tr>
      <th scope="row">
        {duzenlenen !== null ? (
          <form
            className="satir-eylem"
            onSubmit={(olay) => {
              olay.preventDefault();
              if (yeniAd) duzelt.mutate(yeniAd);
            }}
          >
            <input
              value={duzenlenen}
              onChange={(o) => setDuzenlenen(o.target.value)}
              aria-label={tr.personel.adiDuzelt}
              autoFocus
              className="alan alan--orta"
            />
            <Dugme boyut="kucuk" type="submit" disabled={!yeniAd || duzelt.isPending}>
              {tr.personel.adKaydet}
            </Dugme>
            <Dugme
              gorunum="ikincil"
              boyut="kucuk"
              type="button"
              onClick={() => setDuzenlenen(null)}
            >
              {tr.personel.adVazgec}
            </Dugme>
          </form>
        ) : (
          kisi.full_name
        )}
        {duzelt.isError && (
          <p role="alert" className="meta meta--hata">
            {duzeltmeProblemi?.title ?? tr.hata.genel}
          </p>
        )}
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
      </th>
      <td>
        {kisi.assignments.length === 0 ? (
          <span className="durum-metni">—</span>
        ) : (
          kisi.assignments.map((atama, sira) => (
            <div key={`${atama.role}-${sira}`} className="ikincil-metin">
              {atama.role_label}
              {atama.scope_type !== 'tenant' && (
                <span className="durum-metni"> · {kapsamAdi(atama.scope_id)}</span>
              )}
            </div>
          ))
        )}
      </td>
      <td className="sayisal">{kisi.phone ?? '—'}</td>
      <td className="eylem">
        <div className="satir-eylem">
          {kisi.status !== 'masked' && duzenlenen === null && (
            <Dugme
              gorunum="ikincil"
              boyut="kucuk"
              type="button"
              onClick={() => setDuzenlenen(kisi.full_name)}
            >
              {tr.personel.adiDuzelt}
            </Dugme>
          )}
          {kisi.status === 'active' && (
            <Dugme
              gorunum="ikincil"
              boyut="kucuk"
              type="button"
              onClick={() => pasiflestir.mutate()}
            >
              {tr.personel.pasiflestir}
            </Dugme>
          )}
          {kisi.status !== 'masked' &&
            (maskeOnayi ? (
              <Dugme
                gorunum="ikincil"
                boyut="kucuk"
                type="button"
                className="dugme--tehlike"
                onClick={() => maskele.mutate()}
              >
                {tr.personel.maskeleOnay}
              </Dugme>
            ) : (
              <Dugme
                gorunum="ikincil"
                boyut="kucuk"
                type="button"
                onClick={() => setMaskeOnayi(true)}
              >
                {tr.personel.maskele}
              </Dugme>
            ))}
        </div>
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
    >
      <fieldset className="alan-grubu alan-grubu--ayri">
        <legend>{tr.personel.yeniDavet}</legend>
        <div className="yigin yigin--dar">
          <div className="alan-sirasi">
            <label className="alan-etiket">
              {tr.personel.ad}
              <input
                value={ad}
                onChange={(o) => setAd(o.target.value)}
                required
                className="alan alan--orta"
              />
            </label>
            <label className="alan-etiket">
              {tr.personel.telefon}
              <input
                value={telefon}
                onChange={(o) => setTelefon(o.target.value)}
                required
                placeholder="0532 123 45 67"
                className="alan alan--orta"
              />
            </label>
            <label className="alan-etiket">
              {tr.personel.rol}
              <select value={rol} onChange={(o) => setRol(o.target.value as Rol)} className="alan">
                {ROLLER.map((r) => (
                  <option key={r.deger} value={r.deger}>
                    {r.etiket}
                  </option>
                ))}
              </select>
            </label>
            {kapsamGerekli && (
              <label className="alan-etiket">
                {secili?.kapsam === 'bolge' ? tr.personel.bolge : tr.personel.sube}
                <select
                  value={kapsam}
                  onChange={(o) => setKapsam(o.target.value)}
                  required
                  className="alan"
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
            <Dugme type="submit" disabled={davet.isPending}>
              {tr.personel.davet}
            </Dugme>
          </div>

          {davet.isError && (
            <p role="alert" className="bildiri bildiri--hata">
              {problem ? problem.title : tr.hata.genel}
              {problem?.errors?.length ? `: ${problem.errors[0].sebep}` : ''}
            </p>
          )}
          {davet.isSuccess && (
            <p role="status" className="bildiri">
              {tr.personel.davetKuyrukta}
            </p>
          )}
        </div>
      </fieldset>
    </form>
  );
}

function kapsamAdiCozucu(adlar: Map<string, string>) {
  return (id: string | null | undefined) =>
    id ? (adlar.get(id) ?? tr.personel.bilinmeyenKapsam) : '';
}
