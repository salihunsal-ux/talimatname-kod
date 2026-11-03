import type { ReactNode } from 'react';

import type { Bolum } from '../App';
import { rolVar, useBen } from '../api/yetki';
import { tr } from '../i18n/tr';
import { Dugme } from './Dugme';
import { Marka } from './Marka';

/**
 * Yönetim paneli kabuğu: üst bant + gezinme + içerik.
 *
 * Yerleşim CSS ızgarasıyla: dar ekranda yan menü yatay şeride iniyor
 * (`bilesenler.css`), çünkü şube müdürü paneli telefondan da açıyor.
 */
const BOLUMLER: { anahtar: Bolum | null; ad: string; yonetim?: boolean }[] = [
  { anahtar: 'pano', ad: tr.gezinme.pano },
  { anahtar: 'subeler', ad: tr.gezinme.subeler },
  { anahtar: 'personel', ad: tr.gezinme.personel, yonetim: true },
  { anahtar: 'sablonlar', ad: tr.gezinme.sablonlar },
  { anahtar: 'planlar', ad: tr.gezinme.planlar },
  { anahtar: 'aksiyonlar', ad: tr.gezinme.aksiyonlar },
  { anahtar: 'bildirimler', ad: tr.gezinme.bildirimler, yonetim: true },
  { anahtar: 'raporlar', ad: tr.gezinme.raporlar },
  { anahtar: 'kurulum', ad: tr.gezinme.kurulum, yonetim: true },
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
    <div className="kabuk">
      <header className="kabuk-bant">
        <span className="kabuk-marka">
          <Marka koyu boyut={22} />
          {tr.uygulama.ad}
        </span>
        <span className="meta">{tr.uygulama.aciklama}</span>

        {kullanici && (
          <div className="kabuk-kisi">
            <span>
              {kullanici.ad}
              <span style={{ color: 'var(--renk-sessiz)' }}> · {kullanici.rol}</span>
            </span>
            <Dugme gorunum="ikincil" type="button" onClick={onCikis}>
              {tr.giris.cikis}
            </Dugme>
          </div>
        )}
      </header>

      <div className="kabuk-govde">
        <nav aria-label={tr.gezinme.pano} className="kabuk-menu">
          {BOLUMLER.filter((b) => !b.yonetim || yonetim).map(({ anahtar, ad }) => {
            const etkin = anahtar !== null;
            return (
              <button
                key={ad}
                type="button"
                className="dugme menu-dugme"
                disabled={!etkin}
                aria-current={anahtar === bolum}
                onClick={() => anahtar && onBolum(anahtar)}
                title={etkin ? undefined : tr.gezinme.henuzYok}
              >
                {ad}
              </button>
            );
          })}
        </nav>

        <main className="kabuk-icerik">{children}</main>
      </div>
    </div>
  );
}
