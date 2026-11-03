import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import {
  bekleyenVar,
  ciktiDosyasi,
  ciktilarim,
  type CiktiIsi,
  type PdfSonucu,
} from '../../api/ciktilar';
import { kanitBaglantisi } from '../../api/kanitlar';
import {
  aylikOzet,
  aylikOzetPdf,
  dosyayiIndir,
  kanitGalerisi,
  olcumGunlugu,
  olcumGunluguPdf,
  type AylikOzet,
  type GaleriKanidi,
  type OlcumSerisi,
} from '../../api/raporlar';
import { Cip } from '../../bilesenler/Cip';
import { tr } from '../../i18n/tr';
import { Dugme } from '../../bilesenler/Dugme';
import { Hata, Yukleniyor } from '../../bilesenler/Durum';

type Sekme = 'ozet' | 'olcum' | 'galeri';

/**
 * SCR-W-09 · Raporlar (ST-090): aylık özet (FR-1220), ölçüm günlüğü
 * (FR-1207) ve kanıt galerisi (FR-1208).
 *
 * Üçü de denetim konuşmasının parçası — bu yüzden aynı sayfada:
 * "ay nasıl geçti", "sıcaklıklar ne durumda", "kanıtı göster".
 */
export function RaporlarSayfasi() {
  const [sekme, setSekme] = useState<Sekme>('ozet');
  const bugun = new Date();
  const [yil, setYil] = useState(bugun.getFullYear());
  const [ay, setAy] = useState(bugun.getMonth() + 1);

  return (
    <div>
      <header className="sayfa-basligi">
        <div>
          <h1>{tr.rapor.baslik}</h1>
          <p className="sayfa-basligi-alt">{tr.rapor.altBaslik}</p>
        </div>
      </header>

      <div role="tablist" aria-label={tr.rapor.baslik} className="sekme-serit">
        {(
          [
            ['ozet', tr.rapor.aylikOzet],
            ['olcum', tr.rapor.olcumGunlugu],
            ['galeri', tr.rapor.galeri],
          ] as const
        ).map(([anahtar, ad]) => (
          <Dugme
            key={anahtar}
            gorunum="ikincil"
            boyut="kucuk"
            role="tab"
            aria-selected={sekme === anahtar}
            onClick={() => setSekme(anahtar)}
          >
            {ad}
          </Dugme>
        ))}
      </div>

      {sekme === 'ozet' && <AylikOzetBolumu yil={yil} ay={ay} onYil={setYil} onAy={setAy} />}
      {sekme === 'olcum' && <OlcumBolumu />}
      {sekme === 'galeri' && <GaleriBolumu />}

      <CiktilarBolumu />
    </div>
  );
}

/**
 * PDF indirme düğmesi (FR-1220, FR-1214).
 *
 * Kendi durumunu tutuyor: PDF sunucuda üretiliyor ve 60 şubelik bir
 * ayda bu bir saniyeyi geçebiliyor. Tıklayıp hiçbir şey olmaması,
 * kullanıcıyı ikinci kez tıklamaya iter.
 */
function PdfDugmesi({ uret, dosyaAdi }: { uret: () => Promise<PdfSonucu>; dosyaAdi: string }) {
  const [durum, setDurum] = useState<'bos' | 'calisiyor' | 'hata' | 'kuyrukta'>('bos');
  const sorgular = useQueryClient();

  async function tikla() {
    setDurum('calisiyor');
    try {
      const sonuc = await uret();
      if (sonuc.tur === 'is') {
        // Eşiği geçen dönem: sunucu dosya yerine iş kaydı döndü
        // (FR-1217). Liste aşağıda, hazır olunca orada görünecek.
        setDurum('kuyrukta');
        void sorgular.invalidateQueries({ queryKey: ['ciktilar'] });
        return;
      }
      dosyayiIndir(sonuc.blob, dosyaAdi);
      setDurum('bos');
    } catch {
      setDurum('hata');
    }
  }

  return (
    <div className="yigin yigin--dar">
      <Dugme gorunum="ikincil" type="button" onClick={tikla} disabled={durum === 'calisiyor'}>
        {durum === 'calisiyor' ? tr.rapor.pdfHazirlaniyor : tr.rapor.pdfIndir}
      </Dugme>
      {durum === 'hata' && (
        <p role="alert" className="bildiri bildiri--hata">
          {tr.rapor.pdfHata}
        </p>
      )}
      {durum === 'kuyrukta' && (
        <p role="status" className="bildiri">
          {tr.cikti.kuyruga}
        </p>
      )}
    </div>
  );
}

/**
 * Hazırlanan çıktılar (FR-1217).
 *
 * Eşiği geçen dönem raporu arka planda üretiliyor; kullanıcı neyin
 * nerede olduğunu buradan görüyor. Bildirim de düşüyor ama panelde
 * ikinci bir yol olmalı: bildirim sürücüsü bağlı değilken (ST-044)
 * tek yol o olsaydı, çıktı kaybolmuş gibi görünürdü.
 */
function CiktilarBolumu() {
  const isler = useQuery({
    queryKey: ['ciktilar'],
    queryFn: ciktilarim,
    // Üretilen iş varken tazele: kullanıcı sayfayı yenilemek zorunda
    // kalmasın. Hepsi bittiğinde yoklama da duruyor.
    refetchInterval: (sorgu) => (bekleyenVar(sorgu.state.data ?? []) ? 5000 : false),
  });

  if (!isler.data || isler.data.length === 0) return null;

  return (
    <section className="alan-grubu--ayri">
      <header className="bolum-basligi">
        <h2>{tr.cikti.baslik}</h2>
        <p>{tr.cikti.aciklama}</p>
      </header>
      <ul className="liste-yigin">
        {isler.data.map((is) => (
          <CiktiSatiri key={is.id} is={is} />
        ))}
      </ul>
    </section>
  );
}

function CiktiSatiri({ is }: { is: CiktiIsi }) {
  const [hata, setHata] = useState(false);

  async function indir() {
    setHata(false);
    try {
      dosyayiIndir(await ciktiDosyasi(is.id), `${is.kind}-${is.id.slice(0, 8)}.pdf`);
    } catch {
      setHata(true);
    }
  }

  return (
    <li className="madde-satiri">
      <span className="madde-satiri-ad">
        {is.kind_label} · {donemMetni(is)}
      </span>
      <Cip
        renk={is.state === 'ready' ? 'marka' : is.state === 'failed' ? 'kritik' : 'nötr'}
        metin={is.state_label}
      />
      <span className="meta">{tr.cikti.calistirma(is.run_count)}</span>
      <span className="madde-satiri-eylem">
        {is.downloadable && (
          <Dugme gorunum="ikincil" boyut="kucuk" type="button" onClick={() => void indir()}>
            {tr.rapor.pdfIndir}
          </Dugme>
        )}
        {is.state === 'ready' && !is.downloadable && (
          <span className="meta">{tr.cikti.suresiDoldu}</span>
        )}
        {is.state === 'failed' && (
          <span className="hata-metni">{tr.cikti.uretilemedi(is.error_code ?? '')}</span>
        )}
        {hata && (
          <span role="alert" className="hata-metni">
            {tr.rapor.pdfHata}
          </span>
        )}
      </span>
    </li>
  );
}

/** Kâğıdın dönemi: iki tür iki farklı parametre taşıyor. */
function donemMetni(is: CiktiIsi): string {
  if (is.kind === 'aylik-ozet') {
    const ay = Number(is.params.month ?? 0);
    return `${tr.rapor.aylar[ay - 1] ?? ''} ${is.params.year ?? ''}`.trim();
  }
  return `${is.params.first_day ?? ''} – ${is.params.last_day ?? ''}`;
}

function aralik(gunSayisi: number): { ilk: string; son: string } {
  const son = new Date();
  const ilk = new Date(son.getTime() - gunSayisi * 24 * 60 * 60 * 1000);
  return { ilk: ilk.toISOString().slice(0, 10), son: son.toISOString().slice(0, 10) };
}

function AylikOzetBolumu({
  yil,
  ay,
  onYil,
  onAy,
}: {
  yil: number;
  ay: number;
  onYil: (y: number) => void;
  onAy: (a: number) => void;
}) {
  const ozet = useQuery({ queryKey: ['rapor-aylik', yil, ay], queryFn: () => aylikOzet(yil, ay) });

  return (
    <section className="yigin">
      <div className="suzgec-serit">
        <label className="alan-etiket">
          {tr.rapor.ay}
          <select value={ay} onChange={(o) => onAy(Number(o.target.value))} className="alan">
            {tr.rapor.aylar.map((ad, sira) => (
              <option key={ad} value={sira + 1}>
                {ad}
              </option>
            ))}
          </select>
        </label>
        <label className="alan-etiket">
          {tr.rapor.yil}
          <input
            type="number"
            value={yil}
            min={2020}
            max={2100}
            onChange={(o) => onYil(Number(o.target.value))}
            className="alan alan--dar"
          />
        </label>
        <PdfDugmesi
          uret={() => aylikOzetPdf(yil, ay)}
          dosyaAdi={`talimatname-${yil}-${String(ay).padStart(2, '0')}-aylik-ozet.pdf`}
        />
      </div>
      <p className="alan-ipucu">{tr.rapor.pdfAciklama}</p>

      {ozet.isPending && <Yukleniyor />}
      {ozet.isError && <Hata metin={tr.hata.aglaBaglanilamadi} />}
      {ozet.data && <OzetKartlari ozet={ozet.data} />}
      {ozet.data && ozet.data.branches.length > 0 && <SubeTablosu ozet={ozet.data} />}
      {ozet.data && ozet.data.counters.total === 0 && (
        <p className="bos-durum">{tr.rapor.kayitYok}</p>
      )}
    </section>
  );
}

function OzetKartlari({ ozet }: { ozet: AylikOzet }) {
  const s = ozet.counters;
  // Anahtar etiketten değil alandan: iki kart aynı sözcükle
  // başlayabiliyor ("Zamanında tamamlanma" ve "Zamanında").
  const kartlar: [string, string, string][] = [
    ['yuzde', tr.rapor.zamanindaYuzde, s.on_time_percent === null ? '—' : `%${s.on_time_percent}`],
    ['toplam', tr.rapor.toplam, String(s.total)],
    ['zamaninda', tr.rapor.zamaninda, String(s.on_time)],
    ['gec', tr.rapor.gec, String(s.late)],
    ['kacirilan', tr.rapor.kacirilan, String(s.missed)],
    ['basarisiz', tr.rapor.basarisiz, String(s.failed)],
    ['yapilamadi', tr.rapor.yapilamadi, String(s.not_done_items)],
    ['acik', tr.rapor.acik, String(s.open)],
  ];

  return (
    <div className="kutu-izgara">
      {kartlar.map(([anahtar, ad, deger]) => (
        <div key={anahtar} className="kutu">
          <div className="kutu-ad">{ad}</div>
          <div className="kutu-deger">{deger}</div>
        </div>
      ))}
    </div>
  );
}

function SubeTablosu({ ozet }: { ozet: AylikOzet }) {
  return (
    <section>
      <header className="bolum-basligi">
        <h2>{tr.rapor.subeKirilimi}</h2>
        <p>{tr.rapor.siraAciklamasi}</p>
      </header>
      <div className="tablo-kaydirma">
        <table className="tablo">
          <thead>
            <tr>
              <th>{tr.rapor.sube}</th>
              <th className="sayisal">{tr.rapor.zamanindaYuzde}</th>
              <th className="sayisal">{tr.rapor.zamaninda}</th>
              <th className="sayisal">{tr.rapor.gec}</th>
              <th className="sayisal">{tr.rapor.kacirilan}</th>
              <th className="sayisal">{tr.rapor.basarisiz}</th>
            </tr>
          </thead>
          <tbody>
            {ozet.branches.map((sube) => (
              <tr key={sube.branch_id}>
                <th scope="row">
                  {sube.branch_name} <span className="kod">{sube.branch_code}</span>
                </th>
                <td className="sayisal">
                  {sube.counters.on_time_percent === null ? (
                    <span className="durum-metni">{tr.rapor.olculemedi}</span>
                  ) : (
                    `%${sube.counters.on_time_percent}`
                  )}
                </td>
                <td className="sayisal">{sube.counters.on_time}</td>
                <td className="sayisal">{sube.counters.late}</td>
                <td className="sayisal">{sube.counters.missed}</td>
                <td className="sayisal">{sube.counters.failed}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function OlcumBolumu() {
  const [yalnizAralikDisi, setYalnizAralikDisi] = useState(false);
  const { ilk, son } = aralik(30);
  const seriler = useQuery({
    queryKey: ['rapor-olcum', ilk, son, yalnizAralikDisi],
    queryFn: () => olcumGunlugu(ilk, son, yalnizAralikDisi),
  });

  return (
    <section className="yigin">
      <div className="suzgec-serit">
        <label className="onay-etiketi">
          <input
            type="checkbox"
            checked={yalnizAralikDisi}
            onChange={(o) => setYalnizAralikDisi(o.target.checked)}
          />
          {tr.rapor.yalnizAralikDisi}
        </label>
        <PdfDugmesi
          uret={() => olcumGunluguPdf(ilk, son, yalnizAralikDisi)}
          dosyaAdi={`talimatname-olcum-gunlugu-${ilk.replaceAll('-', '')}-${son.replaceAll('-', '')}.pdf`}
        />
      </div>
      <p className="alan-ipucu">{tr.rapor.olcumAciklamasi}</p>

      {seriler.isPending && <Yukleniyor />}
      {seriler.data?.length === 0 && <p className="bos-durum">{tr.rapor.olcumYok}</p>}
      {(seriler.data ?? []).map((seri) => (
        <OlcumSerisiKarti key={seri.item_id} seri={seri} />
      ))}
    </section>
  );
}

function OlcumSerisiKarti({ seri }: { seri: OlcumSerisi }) {
  const aralikMetni =
    seri.min_value !== null && seri.max_value !== null
      ? `${seri.min_value}–${seri.max_value}${seri.unit ?? ''}`
      : '—';

  return (
    <article className="kart">
      <div className="yigin yigin--dar">
        <div className="kart-serit">
          <h3 className="kart-serit-ad" id={`seri-${seri.item_id}`}>
            {seri.item_title}
          </h3>
          <Cip renk="nötr" metin={tr.rapor.kabulAraligi.replace('{a}', aralikMetni)} />
          {seri.out_of_range_count > 0 ? (
            <Cip
              renk="kritik"
              ikon="!"
              metin={tr.rapor.aralikDisiSayisi.replace('{n}', String(seri.out_of_range_count))}
            />
          ) : (
            <Cip renk="marka" ikon="✓" metin={tr.rapor.hepsiAralikta} />
          )}
        </div>

        <div className="tablo-kaydirma">
          <table className="tablo" aria-labelledby={`seri-${seri.item_id}`}>
            <thead>
              <tr>
                <th>{tr.rapor.olcumZamani}</th>
                <th className="sayisal">{tr.rapor.olcumDegeri}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {seri.points.slice(-12).map((nokta, sira) => (
                <tr key={`${nokta.run_id}-${sira}`}>
                  <th scope="row">
                    {nokta.measured_at ? new Date(nokta.measured_at).toLocaleString('tr-TR') : '—'}
                  </th>
                  <td className="sayisal">
                    {nokta.value}
                    {seri.unit ?? ''}
                  </td>
                  <td>
                    {nokta.out_of_range && (
                      <Cip renk="kritik" ikon="!" metin={tr.rapor.aralikDisi} />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </article>
  );
}

function GaleriBolumu() {
  const [yalnizBayrakli, setYalnizBayrakli] = useState(false);
  const { ilk, son } = aralik(14);
  const kanitlar = useQuery({
    queryKey: ['rapor-galeri', ilk, son, yalnizBayrakli],
    queryFn: () => kanitGalerisi(ilk, son, yalnizBayrakli),
  });

  return (
    <section className="yigin">
      <div className="suzgec-serit">
        <label className="onay-etiketi">
          <input
            type="checkbox"
            checked={yalnizBayrakli}
            onChange={(o) => setYalnizBayrakli(o.target.checked)}
          />
          {tr.rapor.yalnizBayrakli}
        </label>
      </div>

      {kanitlar.isPending && <Yukleniyor />}
      {kanitlar.data?.length === 0 && <p className="bos-durum">{tr.rapor.kanitYok}</p>}

      <div className="kanit-izgara">
        {(kanitlar.data ?? []).map((kanit) => (
          <GaleriKarti key={kanit.id} kanit={kanit} />
        ))}
      </div>
    </section>
  );
}

function GaleriKarti({ kanit }: { kanit: GaleriKanidi }) {
  // Çalıştırma detayındaki ile aynı kural: açılamayan görsel kırık
  // simge değil, ne olduğunu söyleyen bir kutu olmalı.
  const [acilmadi, setAcilmadi] = useState(false);
  const baglanti = useQuery({
    queryKey: ['kanit-baglanti', kanit.id, 'thumbnail'],
    queryFn: () => kanitBaglantisi(kanit.id, 'thumbnail'),
    staleTime: 10 * 60 * 1000,
  });

  return (
    <figure className="kanit-cerceve">
      {baglanti.data && !acilmadi ? (
        <img
          src={baglanti.data}
          alt={tr.kanit.gorselAlt}
          onError={() => setAcilmadi(true)}
          className="kanit-gorsel"
        />
      ) : (
        <div className="kanit-yer">
          {baglanti.isError || acilmadi ? tr.kanit.acilamadi : tr.genel.yukleniyor}
        </div>
      )}
      <figcaption className="kanit-alt">
        {new Date(kanit.captured_at ?? kanit.created_at).toLocaleString('tr-TR')}
        {kanit.flags && kanit.flags.length > 0 && (
          <span className="kanit-bayrak">⚑ {kanit.flags.join(' · ')}</span>
        )}
      </figcaption>
    </figure>
  );
}
