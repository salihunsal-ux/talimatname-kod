import type { ReactNode } from 'react';

import type { Bolum } from '../App';
import { tr } from '../i18n/tr';

/**
 * Yönetim paneli kabuğu: başlık + gezinme + içerik.
 * Gezinmenin iki bölümü bağlı; kalanı sırayla açılacak
 * (ST-013 personel, ST-016 şablonlar, ST-029 planlar…).
 */
const BOLUMLER: { anahtar: Bolum | null; ad: string }[] = [
  { anahtar: null, ad: tr.gezinme.pano },
  { anahtar: 'subeler', ad: tr.gezinme.subeler },
  { anahtar: 'personel', ad: tr.gezinme.personel },
  { anahtar: null, ad: tr.gezinme.sablonlar },
  { anahtar: null, ad: tr.gezinme.planlar },
  { anahtar: null, ad: tr.gezinme.aksiyonlar },
  { anahtar: null, ad: tr.gezinme.raporlar },
  { anahtar: 'sistem', ad: tr.sistem.baslik },
];

export function Kabuk({
  children,
  bolum,
  onBolum,
}: {
  children: ReactNode;
  bolum: Bolum;
  onBolum: (yeni: Bolum) => void;
}) {
  return (
    <div style={{ minHeight: '100vh' }}>
      <header
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 'var(--bosluk-3)',
          flexWrap: 'wrap',
          padding: 'var(--bosluk-4) var(--bosluk-6)',
          background: 'var(--renk-yuzey)',
          borderBottom: '1px solid var(--renk-cizgi)',
        }}
      >
        <strong style={{ fontSize: 'var(--baslik-bolum)' }}>{tr.uygulama.ad}</strong>
        <span style={{ color: 'var(--renk-sessiz)', fontSize: 'var(--meta)' }}>
          {tr.uygulama.aciklama}
        </span>
      </header>

      <div style={{ display: 'flex', alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <nav
          aria-label={tr.gezinme.pano}
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--bosluk-1)',
            padding: 'var(--bosluk-4)',
            minWidth: 180,
          }}
        >
          {BOLUMLER.map(({ anahtar, ad }) => {
            const etkin = anahtar !== null;
            const secili = anahtar === bolum;
            return (
              <button
                key={ad}
                type="button"
                disabled={!etkin}
                aria-current={secili}
                onClick={() => anahtar && onBolum(anahtar)}
                title={etkin ? undefined : tr.gezinme.henuzYok}
                style={{
                  textAlign: 'left',
                  padding: '0 var(--bosluk-3)',
                  border: '1px solid',
                  borderColor: secili ? 'var(--renk-marka)' : 'transparent',
                  borderRadius: 'var(--kose-dugme)',
                  background: secili ? 'var(--renk-marka-acik)' : 'transparent',
                  color: etkin ? 'var(--renk-murekkep)' : 'var(--renk-sessiz)',
                  cursor: etkin ? 'pointer' : 'not-allowed',
                }}
              >
                {ad}
              </button>
            );
          })}
        </nav>

        <main style={{ flex: 1, minWidth: 320, padding: 'var(--bosluk-4) var(--bosluk-6)' }}>
          {children}
        </main>
      </div>
    </div>
  );
}
