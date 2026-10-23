import type { ReactNode } from 'react';

import type { Bolum } from '../App';
import { rolVar, useBen } from '../api/yetki';
import { tr } from '../i18n/tr';

/**
 * Yönetim paneli kabuğu: başlık + gezinme + içerik.
 * Gezinmenin iki bölümü bağlı; kalanı sırayla açılacak
 * (ST-013 personel, ST-016 şablonlar, ST-029 planlar…).
 */
const BOLUMLER: { anahtar: Bolum | null; ad: string; yonetim?: boolean }[] = [
  { anahtar: 'pano', ad: tr.gezinme.pano },
  { anahtar: 'subeler', ad: tr.gezinme.subeler },
  { anahtar: 'personel', ad: tr.gezinme.personel, yonetim: true },
  { anahtar: 'sablonlar', ad: tr.gezinme.sablonlar },
  { anahtar: 'planlar', ad: tr.gezinme.planlar },
  { anahtar: 'aksiyonlar', ad: tr.gezinme.aksiyonlar },
  { anahtar: null, ad: tr.gezinme.raporlar },
  { anahtar: 'sistem', ad: tr.sistem.baslik },
];

export function Kabuk({
  children,
  bolum,
  onBolum,
  kullanici,
  onCikis,
}: {
  children: ReactNode;
  bolum: Bolum;
  onBolum: (yeni: Bolum) => void;
  kullanici?: { ad: string; rol: string };
  onCikis?: () => void;
}) {
  // Açılamayacak bölüm menüde durmasın: 403 görmek bilgi değil, sürtünme.
  const yonetim = rolVar(useBen(), 'admin', 'region_manager');

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

        {kullanici && (
          <div
            style={{
              marginLeft: 'auto',
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--bosluk-3)',
            }}
          >
            <span style={{ fontSize: 'var(--meta)', color: 'var(--renk-murekkep2)' }}>
              {kullanici.ad}
              <span style={{ color: 'var(--renk-sessiz)' }}> · {kullanici.rol}</span>
            </span>
            <button
              type="button"
              onClick={onCikis}
              style={{
                minHeight: 36,
                padding: '0 var(--bosluk-3)',
                border: '1px solid var(--renk-cizgi)',
                borderRadius: 'var(--kose-dugme)',
                background: 'transparent',
                color: 'var(--renk-murekkep)',
                cursor: 'pointer',
              }}
            >
              {tr.giris.cikis}
            </button>
          </div>
        )}
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
          {BOLUMLER.filter((b) => !b.yonetim || yonetim).map(({ anahtar, ad }) => {
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
