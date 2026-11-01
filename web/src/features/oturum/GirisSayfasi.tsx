import { useState } from 'react';

import { problemCoz } from '../../api/client';
import { kodDogrula, kodIste, type KodYaniti } from '../../api/oturum';
import { tr } from '../../i18n/tr';

/**
 * Giriş: telefon → kod → oturum (ST-004; FR-0201, FR-0203).
 *
 * SMS sağlayıcısı bağlı olmadığı için "kod gönderildi" **yazmıyoruz**;
 * sunucu `delivered: false` döndürüyor, ekran da bunu olduğu gibi
 * söylüyor ve geliştirme ortamında kodu gösteriyor. Sağlayıcı
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
    <main
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: 'var(--bosluk-4)',
      }}
    >
      <section
        aria-labelledby="giris-baslik"
        style={{
          background: 'var(--renk-yuzey)',
          border: '1px solid var(--renk-cizgi)',
          borderRadius: 'var(--kose-kart)',
          padding: 'var(--bosluk-5)',
          width: '100%',
          maxWidth: 380,
        }}
      >
        <h1 id="giris-baslik" style={{ fontSize: 'var(--baslik-bolum)', margin: 0 }}>
          {tr.uygulama.ad}
        </h1>
        <p style={{ color: 'var(--renk-sessiz)', fontSize: 'var(--meta)', marginTop: 4 }}>
          {tr.giris.aciklama}
        </p>

        {adim === 'telefon' ? (
          <form
            onSubmit={(olay) => {
              olay.preventDefault();
              void calistir(async () => {
                const yanit = await kodIste(telefon);
                setBilgi(yanit);
                setAdim('kod');
              });
            }}
          >
            <label htmlFor="giris-telefon" style={etiket}>
              {tr.giris.telefon}
            </label>
            <input
              id="giris-telefon"
              type="tel"
              autoComplete="tel"
              inputMode="tel"
              required
              value={telefon}
              onChange={(olay) => setTelefon(olay.target.value)}
              placeholder={tr.giris.telefonOrnek}
              style={alan}
            />
            <button type="submit" disabled={calisiyor} style={dugme}>
              {calisiyor ? tr.genel.yukleniyor : tr.giris.kodIste}
            </button>
          </form>
        ) : (
          <form
            onSubmit={(olay) => {
              olay.preventDefault();
              void calistir(async () => {
                await kodDogrula(telefon, kod);
                onGiris();
              });
            }}
          >
            {bilgi != null && !bilgi.delivered && (
              <p role="status" style={uyari}>
                {tr.giris.gonderilmedi}
                {bilgi.dev_code !== null && bilgi.dev_code !== undefined && (
                  <>
                    {' '}
                    <strong>{tr.giris.gelistirmeKodu(bilgi.dev_code)}</strong>
                  </>
                )}
              </p>
            )}

            <label htmlFor="giris-kod" style={etiket}>
              {tr.giris.kod}
            </label>
            <input
              id="giris-kod"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              value={kod}
              onChange={(olay) => setKod(olay.target.value)}
              style={{ ...alan, letterSpacing: '0.3em' }}
            />
            <button type="submit" disabled={calisiyor} style={dugme}>
              {calisiyor ? tr.genel.yukleniyor : tr.giris.gir}
            </button>
            <button
              type="button"
              onClick={() => {
                setAdim('telefon');
                setKod('');
                setHata(null);
              }}
              style={{ ...dugme, background: 'transparent', color: 'var(--renk-murekkep2)' }}
            >
              {tr.giris.numarayiDegistir}
            </button>
          </form>
        )}

        {hata !== null && (
          <p role="alert" style={{ color: 'var(--renk-kritik)', marginTop: 'var(--bosluk-3)' }}>
            {hata}
          </p>
        )}

        {/* Belge doğrulama oturum istemiyor (FR-1218); kâğıdı eline alan
            buraya da gelebilsin diye giriş ekranında duruyor. */}
        <a
          href="/dogrula"
          style={{
            display: 'inline-block',
            marginTop: 'var(--bosluk-4)',
            fontSize: 'var(--meta)',
            color: 'var(--renk-marka)',
          }}
        >
          {tr.giris.belgeDogrula}
        </a>
      </section>
    </main>
  );
}

const etiket = {
  display: 'block',
  marginTop: 'var(--bosluk-4)',
  fontSize: 'var(--meta)',
  color: 'var(--renk-murekkep2)',
} as const;

const alan = {
  width: '100%',
  minHeight: 44,
  marginTop: 4,
  padding: '0 var(--bosluk-3)',
  border: '1px solid var(--renk-cizgi)',
  borderRadius: 'var(--kose-dugme)',
  background: 'var(--renk-zemin)',
  color: 'var(--renk-murekkep)',
  boxSizing: 'border-box',
} as const;

const dugme = {
  width: '100%',
  minHeight: 44,
  marginTop: 'var(--bosluk-3)',
  border: '1px solid var(--renk-marka)',
  borderRadius: 'var(--kose-dugme)',
  background: 'var(--renk-marka)',
  color: '#fff',
  cursor: 'pointer',
} as const;

const uyari = {
  marginTop: 'var(--bosluk-3)',
  padding: 'var(--bosluk-2) var(--bosluk-3)',
  border: '1px solid var(--renk-cizgi)',
  borderRadius: 'var(--kose-kart)',
  background: 'var(--renk-zemin)',
  color: 'var(--renk-murekkep2)',
  fontSize: 'var(--meta)',
} as const;
