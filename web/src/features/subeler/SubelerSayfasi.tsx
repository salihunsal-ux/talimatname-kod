import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { problemCoz } from '../../api/client';
import { subeAgaci, subeDetayi, subeEkle, subePasiflestir } from '../../api/subeler';
import { useYonetici } from '../../api/yetki';
import { tr } from '../../i18n/tr';
import { Cip } from '../../bilesenler/Cip';
import { Dugme } from '../../bilesenler/Dugme';
import { Hata, Yukleniyor } from '../../bilesenler/Durum';
import { IskeletListe } from '../../bilesenler/Iskelet';

/**
 * SCR-W-02 · Şubeler: solda bölge → şube ağacı, sağda şube detayı.
 * Veri bugün bellek içi tohumdan geliyor; veritabanı bağlanınca (ücretsiz
 * bulut PostgreSQL) bu ekran değişmez — aynı uç noktalar.
 */
export function SubelerSayfasi() {
  const yonetici = useYonetici();
  const [secili, setSecili] = useState<string | null>(null);
  const [pasifDahil, setPasifDahil] = useState(false);

  const agac = useQuery({
    queryKey: ['subeler', { pasifDahil }],
    queryFn: () => subeAgaci(pasifDahil),
  });

  const bos = agac.data?.every((bolge) => bolge.branches.length === 0) ?? false;

  return (
    <div>
      <header className="sayfa-basligi">
        <div>
          <h1>{tr.subeler.baslik}</h1>
          <p className="sayfa-basligi-alt">{tr.subeler.altBaslik}</p>
        </div>
        <div className="sayfa-basligi-denetimler">
          <label className="onay-etiketi">
            <input
              type="checkbox"
              checked={pasifDahil}
              onChange={(olay) => setPasifDahil(olay.target.checked)}
            />
            {tr.subeler.pasifleriGoster}
          </label>
        </div>
      </header>

      <div className="liste-detay">
        <div className="liste-detay-kenar">
          {agac.isPending && <IskeletListe satirlar={6} />}
          {agac.isError && <Hata hata={agac.error} metin={tr.hata.aglaBaglanilamadi} />}
          {bos && <p className="bos-durum">{tr.subeler.subeYok}</p>}

          {agac.data?.map((bolge) => (
            <section key={bolge.id ?? 'bolgesiz'}>
              <h2 className="bolum-etiketi">
                {bolge.name} · {bolge.branches.length}
              </h2>
              <ul className="liste-yigin">
                {bolge.branches.map((sube) => (
                  <li key={sube.id}>
                    <button
                      type="button"
                      onClick={() => setSecili(sube.id)}
                      aria-current={secili === sube.id}
                      className="liste-satiri"
                    >
                      <code className="kod">{sube.code}</code>
                      <span className="liste-satiri-ad">{sube.name}</span>
                      {sube.status === 'inactive' ? (
                        <Cip renk="pasif" ikon="–" metin={tr.subeler.pasif} />
                      ) : (
                        <span className="meta">
                          {sube.open_days} {tr.subeler.gunKisaltma}
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}

          {yonetici && <SubeEkleFormu />}
        </div>

        <div>
          {secili ? (
            <SubeDetayi id={secili} onPasiflestirildi={() => setSecili(null)} />
          ) : (
            <p className="bos-durum">{tr.subeler.secimYok}</p>
          )}
        </div>
      </div>
    </div>
  );
}

function SubeDetayi({ id, onPasiflestirildi }: { id: string; onPasiflestirildi: () => void }) {
  const kuyruk = useQueryClient();
  const detay = useQuery({ queryKey: ['sube', id], queryFn: () => subeDetayi(id) });
  const pasiflestir = useMutation({
    mutationFn: () => subePasiflestir(id),
    onSuccess: async () => {
      await kuyruk.invalidateQueries({ queryKey: ['subeler'] });
      await kuyruk.invalidateQueries({ queryKey: ['sube', id] });
      onPasiflestirildi();
    },
  });

  if (detay.isPending) return <Yukleniyor />;
  if (detay.isError || !detay.data) return <Hata hata={detay.error} />;

  const sube = detay.data;

  return (
    <article className="kart">
      <header className="kart-ustu">
        <h2>{sube.name}</h2>
        <code className="kod">{sube.code}</code>
        {sube.status === 'inactive' && <Cip renk="pasif" ikon="–" metin={tr.subeler.pasif} />}
      </header>
      {sube.address && <p>{sube.address}</p>}

      <div className="yigin">
        <section>
          <h3 className="bolum-etiketi">{tr.subeler.calismaSaatleri}</h3>
          <table className="tablo">
            <tbody>
              {sube.business_hours.map((gun) => (
                <tr key={gun.weekday}>
                  <th scope="row">{gun.weekday_name}</th>
                  <td className="sayisal">
                    {gun.open_time ? (
                      `${saat(gun.open_time)} – ${saat(gun.close_time)}`
                    ) : (
                      <span className="durum-metni">{tr.subeler.kapali}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section>
          <h3 className="bolum-etiketi">{tr.subeler.istasyonlar}</h3>
          <ul className="cip-listesi">
            {sube.stations.map((istasyon) => (
              <li key={istasyon.id}>
                <Cip renk="nötr" metin={istasyon.name} />
              </li>
            ))}
          </ul>
        </section>
      </div>

      {sube.status === 'active' && (
        <div className="eylemler">
          <Dugme
            gorunum="ikincil"
            type="button"
            onClick={() => pasiflestir.mutate()}
            disabled={pasiflestir.isPending}
          >
            {tr.subeler.pasiflestir}
          </Dugme>
        </div>
      )}
      <p className="dipnot">{tr.subeler.pasiflestirmeNotu}</p>
    </article>
  );
}

function SubeEkleFormu() {
  const kuyruk = useQueryClient();
  const [kod, setKod] = useState('');
  const [ad, setAd] = useState('');
  const ekle = useMutation({
    // Saat dilimi şimdilik sabit: hesap varsayılanı modellenince (CAP-01)
    // forma seçici gelecek; zincirlerin çoğu tek saat diliminde.
    mutationFn: () => subeEkle({ code: kod, name: ad, timezone: 'Europe/Istanbul' }),
    onSuccess: async () => {
      setKod('');
      setAd('');
      await kuyruk.invalidateQueries({ queryKey: ['subeler'] });
    },
  });

  const problem = problemCoz(ekle.error);

  return (
    <form
      onSubmit={(olay) => {
        olay.preventDefault();
        ekle.mutate();
      }}
    >
      <fieldset className="alan-grubu">
        <legend>{tr.subeler.yeniSube}</legend>
        <div className="yigin yigin--dar">
          <div className="alan-sirasi">
            <label className="alan-etiket">
              {tr.subeler.kod}
              <input
                value={kod}
                onChange={(olay) => setKod(olay.target.value)}
                required
                maxLength={16}
                className="alan alan--dar"
              />
            </label>
            <label className="alan-etiket">
              {tr.subeler.ad}
              <input
                value={ad}
                onChange={(olay) => setAd(olay.target.value)}
                required
                maxLength={80}
                className="alan alan--orta"
              />
            </label>
            <Dugme type="submit" disabled={ekle.isPending}>
              {tr.subeler.ekle}
            </Dugme>
          </div>
          {ekle.isError && (
            <p role="alert" className="bildiri bildiri--hata">
              {problem ? problem.title : tr.hata.genel}
              {problem?.errors?.length ? `: ${problem.errors[0].sebep}` : ''}
            </p>
          )}
        </div>
      </fieldset>
    </form>
  );
}

/** "08:00:00" → "08:00" */
function saat(deger: string | null | undefined): string {
  return deger ? deger.slice(0, 5) : '';
}
