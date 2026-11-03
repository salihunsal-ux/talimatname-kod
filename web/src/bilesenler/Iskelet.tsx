import type { ReactNode } from 'react';

import { useGecikme } from '../gecikme';
import { tr } from '../i18n/tr';

/**
 * İskelet yükleme.
 *
 * Kural: **şekli bilinen yerde** iskelet, bilinmeyen yerde sessiz
 * satır (`Durum.tsx` · `Yukleniyor`). Tablo, liste ve kutu ızgarası
 * şeklini biliyor; kurulum sihirbazının adımı bilmiyor.
 *
 * İskelet gerçek yerleşimin ölçüsünde duruyor — veri gelince sayfa
 * zıplamasın. Ekran okuyucu için değişen bir şey yok: alan
 * `aria-busy` ve içinde aynı "Yükleniyor…" cümlesi var; gri kutular
 * `aria-hidden`.
 */
type Bicim = 'metin' | 'satir' | 'kutu' | 'manset';

/** Sınıf adları düz metin: üretilmiş ad, ölü sınıf kapısından kaçar. */
const BICIM: Record<Bicim, string> = {
  metin: 'iskelet--metin',
  satir: 'iskelet--satir',
  kutu: 'iskelet--kutu',
  manset: 'iskelet--manset',
};

export function Iskelet({ bicim = 'metin', dar = false }: { bicim?: Bicim; dar?: boolean }) {
  const siniflar = ['iskelet', BICIM[bicim], dar ? 'iskelet--dar' : ''].filter(Boolean).join(' ');
  return <span className={siniflar} aria-hidden="true" />;
}

/** Gecikmeyi ve duyuruyu tek yerde tutan sarmalayıcı. */
function Bekleyen({ children }: { children: ReactNode }) {
  const hazir = useGecikme();
  if (!hazir) return null;

  return (
    <div role="status" aria-busy="true" className="yigin yigin--dar">
      <span className="sr-only">{tr.genel.yukleniyor}</span>
      {children}
    </div>
  );
}

export function IskeletTablo({ sutunlar, satirlar = 4 }: { sutunlar: number; satirlar?: number }) {
  return (
    <Bekleyen>
      <div className="tablo-kaydirma">
        <table className="tablo">
          <tbody>
            {Array.from({ length: satirlar }, (_, satir) => (
              <tr key={satir}>
                {Array.from({ length: sutunlar }, (_, sutun) => (
                  <td key={sutun}>
                    {/* Son sütun kısa: gerçek tabloda da orada eylem ya
                        da sayı var, metin değil. */}
                    <Iskelet dar={sutun === sutunlar - 1} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Bekleyen>
  );
}

export function IskeletListe({ satirlar = 4 }: { satirlar?: number }) {
  return (
    <Bekleyen>
      {Array.from({ length: satirlar }, (_, satir) => (
        <Iskelet key={satir} bicim="satir" />
      ))}
    </Bekleyen>
  );
}

export function IskeletKutular({ adet = 4 }: { adet?: number }) {
  return (
    <Bekleyen>
      <div className="kutu-izgara">
        {Array.from({ length: adet }, (_, kutu) => (
          <Iskelet key={kutu} bicim="kutu" />
        ))}
      </div>
    </Bekleyen>
  );
}

/** Pano: koyu manşet + yanındaki sayılar. */
export function IskeletOzet() {
  return (
    <Bekleyen>
      <div className="ozet-serit">
        <Iskelet bicim="manset" />
        <div className="ozet-kutular">
          {Array.from({ length: 5 }, (_, kutu) => (
            <Iskelet key={kutu} bicim="kutu" />
          ))}
        </div>
      </div>
    </Bekleyen>
  );
}
