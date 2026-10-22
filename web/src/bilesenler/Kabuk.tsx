import type { ReactNode } from 'react';

import { tr } from '../i18n/tr';

/**
 * Yönetim paneli kabuğu: başlık + gezinme + içerik.
 * Gezinme öğeleri henüz bağlı değil; rol kapsamı ST-006'da gelecek.
 */
export function Kabuk({ children }: { children: ReactNode }) {
  const bolumler = Object.values(tr.gezinme);

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
          {bolumler.map((ad) => (
            <button
              key={ad}
              type="button"
              disabled
              style={{
                textAlign: 'left',
                padding: '0 var(--bosluk-3)',
                border: '1px solid transparent',
                borderRadius: 'var(--kose-dugme)',
                background: 'transparent',
                color: 'var(--renk-murekkep2)',
                cursor: 'not-allowed',
              }}
            >
              {ad}
            </button>
          ))}
        </nav>

        <main style={{ flex: 1, minWidth: 320, padding: 'var(--bosluk-4) var(--bosluk-6)' }}>
          {children}
        </main>
      </div>
    </div>
  );
}
