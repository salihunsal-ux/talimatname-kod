import { useState } from 'react';

import { problemCoz } from '../../api/client';
import { kodDogrula, kodIste, type KodYaniti } from '../../api/oturum';
import { Alan } from '../../bilesenler/Alan';
import { Dugme } from '../../bilesenler/Dugme';
import { Kart } from '../../bilesenler/Kart';
import { tr } from '../../i18n/tr';

/**
 * Giriş: telefon → kod → oturum (ST-004; FR-0201, FR-0203).
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
      <Kart yuzen className="giris-kart" aria-labelledby="giris-baslik">
        {/* Marka bloğu kartın içinde: işaret dosyası henüz yok, bu
            yüzden yazıyla duruyor (tasarım sistemi · İkonografi). */}
        <div className="giris-marka">
          <h1 id="giris-baslik" className="baslik-ekran">
            {tr.uygulama.ad}
          </h1>
          <p className="meta" style={{ margin: 'var(--bosluk-1) 0 0' }}>
            {tr.giris.aciklama}
          </p>
        </div>

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
              <p role="status" className="bildiri" style={{ margin: 0 }}>
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
            <div className="yigin--dar" style={{ display: 'grid' }}>
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
          <p role="alert" className="bildiri bildiri--hata" style={{ marginBottom: 0 }}>
            {hata}
          </p>
        )}
      </Kart>

      {/* Belge doğrulama oturum istemiyor (FR-1218); kâğıdı eline alan
          buraya da gelebilsin diye giriş ekranında duruyor. */}
      <div className="giris-alt">
        <a href="/dogrula" className="meta" style={{ color: 'var(--renk-marka)' }}>
          {tr.giris.belgeDogrula}
        </a>
      </div>
    </main>
  );
}
