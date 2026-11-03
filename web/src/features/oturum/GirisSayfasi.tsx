import { useState } from 'react';

import { problemCoz } from '../../api/client';
import { kodDogrula, kodIste, type KodYaniti } from '../../api/oturum';
import { Alan } from '../../bilesenler/Alan';
import { Dugme } from '../../bilesenler/Dugme';
import { Marka } from '../../bilesenler/Marka';
import { tr } from '../../i18n/tr';

/**
 * Giriş: telefon → kod → oturum (ST-004; FR-0201, FR-0203).
 *
 * Yerleşim iki bölümlü: solda koyu panel ürünün ne yaptığını söylüyor,
 * sağda form. Telefonda panel kısalıyor ve forma yer açıyor — şube
 * müdürü paneli de telefondan açıyor.
 *
 * Paneldeki üç madde **sayı değil cümle**: giriş ekranında uydurma
 * ölçü göstermek, ürünün tek iddiası "kanıt" olan bir üründe tuhaf
 * olurdu.
 *
 * SMS sağlayıcısı bağlı olmadığı için "kod gönderildi" **yazmıyoruz**;
 * sunucu `delivered: false` döndürüyor, ekran da bunu olduğu gibi
 * söylüyor ve kodu görünür kılan ayar açıksa kodu gösteriyor. Sağlayıcı
 * bağlandığında (ST-067) bu uyarı kendiliğinden kaybolur.
 */
export function GirisSayfasi({ onGiris }: { onGiris: () => void }) {
  const [adim, setAdim] = useState<'telefon' | 'kod'>('telefon');
  const [telefon, setTelefon] = useState('');
  const [kod, setKod] = useState('');
  const [bilgi, setBilgi] = useState<KodYaniti | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [calisiyor, setCalisiyor] = useState(false);

  async function calistir(is: () => Promise<void>) {
    setHata(null);
    setCalisiyor(true);
    try {
      await is();
    } catch (sebep) {
      const problem = problemCoz(sebep);
      setHata(problem ? (problem.detail ?? problem.title) : tr.hata.aglaBaglanilamadi);
    } finally {
      setCalisiyor(false);
    }
  }

  return (
    <main className="giris">
      <section className="giris-panel">
        <div className="giris-marka">
          <Marka boyut={30} koyu />
          {tr.uygulama.ad}
        </div>

        <div>
          <p className="giris-ustbaslik">{tr.giris.ustbaslik}</p>
          <h1 id="giris-baslik" className="giris-vaat">
            {tr.giris.vaat}
          </h1>
          <p className="giris-aciklama">{tr.giris.vaatAciklama}</p>
        </div>

        <ul className="giris-maddeler">
          {tr.giris.ozellikler.map((madde) => (
            <li key={madde}>
              <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" focusable="false">
                <circle cx="9" cy="9" r="8" fill="none" stroke="var(--renk-koyu-marka)" />
                <path
                  d="M5.6 9.2l2.2 2.2 4.5-4.9"
                  fill="none"
                  stroke="var(--renk-koyu-marka)"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              {madde}
            </li>
          ))}
        </ul>
      </section>

      <section className="giris-form" aria-labelledby="giris-form-baslik">
        <div>
          <h2 id="giris-form-baslik" className="baslik-ekran">
            {tr.giris.gir}
          </h2>
          <p className="sayfa-basligi-alt">{tr.giris.aciklama}</p>

          {adim === 'telefon' ? (
            <form
              className="yigin"
              onSubmit={(olay) => {
                olay.preventDefault();
                void calistir(async () => {
                  const yanit = await kodIste(telefon);
                  setBilgi(yanit);
                  setAdim('kod');
                });
              }}
            >
              <Alan
                id="giris-telefon"
                etiket={tr.giris.telefon}
                type="tel"
                autoComplete="tel"
                inputMode="tel"
                required
                value={telefon}
                onChange={(olay) => setTelefon(olay.target.value)}
                placeholder={tr.giris.telefonOrnek}
              />
              <Dugme type="submit" tam disabled={calisiyor}>
                {calisiyor ? tr.genel.yukleniyor : tr.giris.kodIste}
              </Dugme>
              <p className="meta">{tr.giris.kodGelmedi}</p>
            </form>
          ) : (
            <form
              className="yigin"
              onSubmit={(olay) => {
                olay.preventDefault();
                void calistir(async () => {
                  await kodDogrula(telefon, kod);
                  onGiris();
                });
              }}
            >
              {bilgi != null && !bilgi.delivered && (
                <p role="status" className="bildiri">
                  {tr.giris.gonderilmedi}
                  {bilgi.dev_code !== null && bilgi.dev_code !== undefined && (
                    <>
                      {' '}
                      <strong>{tr.giris.ekrandakiKod(bilgi.dev_code)}</strong>
                    </>
                  )}
                </p>
              )}

              <Alan
                id="giris-kod"
                etiket={tr.giris.kod}
                className="alan--kod"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                value={kod}
                onChange={(olay) => setKod(olay.target.value)}
              />
              <div className="yigin yigin--dar">
                <Dugme type="submit" tam disabled={calisiyor}>
                  {calisiyor ? tr.genel.yukleniyor : tr.giris.gir}
                </Dugme>
                <Dugme
                  type="button"
                  gorunum="sessiz"
                  tam
                  onClick={() => {
                    setAdim('telefon');
                    setKod('');
                    setHata(null);
                  }}
                >
                  {tr.giris.numarayiDegistir}
                </Dugme>
              </div>
            </form>
          )}

          {hata !== null && (
            <p role="alert" className="bildiri bildiri--hata">
              {hata}
            </p>
          )}

          {/* Belge doğrulama oturum istemiyor (FR-1218); kâğıdı eline
              alan buraya da gelebilsin diye giriş ekranında duruyor. */}
          <div className="giris-alt">
            <span className="meta">{tr.giris.belgeniz} </span>
            <a href="/dogrula">{tr.giris.belgeDogrula}</a>
          </div>
        </div>
      </section>
    </main>
  );
}
