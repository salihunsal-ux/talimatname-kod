import type { ReactNode } from 'react';

import type { Bolum } from '../App';
import { rolVar, useBen } from '../api/yetki';
import { tr } from '../i18n/tr';
import { Dugme } from './Dugme';
import { Marka } from './Marka';
import { TemaSecici } from './Tema';

/**
 * Yönetim paneli kabuğu: üst bant + gezinme + içerik.
 *
 * Yerleşim CSS ızgarasıyla: dar ekranda yan menü yatay şeride iniyor
 * (`bilesenler.css`), çünkü şube müdürü paneli telefondan da açıyor.
 */
/**
 * Menüdeki kapı sunucudaki kapıyla **birebir** olmalı: gösterilen her
 * madde açılabilmeli. `yonetim` bölge müdürünü de içerir (sunucuda
 * `Mudur`), `yalnizcaYonetici` içermez (sunucuda `Yonetici`). Tek bir
 * bayrak kullanıldığında bölge müdürü Bildirimler ve Kurulum'u menüde
 * görüyor ama 403 alıyordu.
 */
const BOLUMLER: {
  anahtar: Bolum | null;
  ad: string;
  yonetim?: boolean;
  yalnizcaYonetici?: boolean;
}[] = [
  { anahtar: 'pano', ad: tr.gezinme.pano },
  { anahtar: 'subeler', ad: tr.gezinme.subeler },
  { anahtar: 'personel', ad: tr.gezinme.personel, yonetim: true },
  { anahtar: 'sablonlar', ad: tr.gezinme.sablonlar },
  { anahtar: 'planlar', ad: tr.gezinme.planlar },
  { anahtar: 'aksiyonlar', ad: tr.gezinme.aksiyonlar },
  { anahtar: 'bildirimler', ad: tr.gezinme.bildirimler, yalnizcaYonetici: true },
  { anahtar: 'raporlar', ad: tr.gezinme.raporlar },
  { anahtar: 'saha', ad: tr.gezinme.saha },
  { anahtar: 'kurulum', ad: tr.gezinme.kurulum, yalnizcaYonetici: true },
  { anahtar: 'sistem', ad: tr.sistem.baslik },
];

export function Kabuk({
  children,
  bolum,
  onBolum,
  kullanici,
  onCikis,
  menusuz = false,
}: {
  children: ReactNode;
  bolum: Bolum;
  onBolum: (yeni: Bolum) => void;
  kullanici?: { ad: string; rol: string };
  onCikis?: () => void;
  /** Saha istemcisi: üst bant kalır, yan menü yok — personelin
      açabileceği tek ekran zaten bu. */
  menusuz?: boolean;
}) {
  // Açılamayacak bölüm menüde durmasın: 403 görmek bilgi değil, sürtünme.
  const ben = useBen();
  const yonetim = rolVar(ben, 'admin', 'region_manager');
  const yonetici = rolVar(ben, 'admin');

  return (
    <div className="kabuk">
      <header className="kabuk-bant">
        <span className="kabuk-marka">
          <Marka koyu boyut={22} />
          <span className="kabuk-marka-ad">{tr.uygulama.ad}</span>
        </span>
        <span className="meta">{tr.uygulama.aciklama}</span>

        <div className="kabuk-kisi">
          <TemaSecici />
        </div>

        {kullanici && (
          <div className="kabuk-kisi kabuk-kisi--bitisik">
            <span className="kabuk-kisi-kim">
              <span className="kabuk-kisi-ad">{kullanici.ad}</span>
              <span className="kabuk-kisi-rol"> · {kullanici.rol}</span>
            </span>
            <Dugme gorunum="ikincil" type="button" onClick={onCikis}>
              {tr.giris.cikis}
            </Dugme>
          </div>
        )}
      </header>

      <div className={menusuz ? 'kabuk-govde kabuk-govde--menusuz' : 'kabuk-govde'}>
        {!menusuz && (
          <nav aria-label={tr.gezinme.pano} className="kabuk-menu">
            {BOLUMLER.filter(
              (b) => (!b.yonetim || yonetim) && (!b.yalnizcaYonetici || yonetici),
            ).map(({ anahtar, ad }) => {
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
        )}

        <main className="kabuk-icerik">{children}</main>
      </div>
    </div>
  );
}
