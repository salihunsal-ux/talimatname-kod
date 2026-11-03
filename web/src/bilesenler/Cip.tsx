/**
 * Durum çipi (tasarım sistemi · "Durum çipi"): renk tek başına anlam
 * taşımaz, ikon + metin birlikte verilir (NFR-11).
 *
 * Renk çifti `.durum--*` sınıflarında — pano ızgarası da aynı sınıfları
 * kullanıyor. Önce iki kopya vardı: buradaki `RENKLER` haritası ve
 * panonun `HUCRE`'si. Biri değişip öteki kalabilirdi.
 */
export type CipRengi = 'marka' | 'kritik' | 'uyari' | 'pasif' | 'nötr';

/** Sınıf adı ASCII; arayüzdeki ad Türkçe kalıyor. */
const SINIF: Record<CipRengi, string> = {
  marka: 'durum--marka',
  kritik: 'durum--kritik',
  uyari: 'durum--uyari',
  pasif: 'durum--pasif',
  nötr: 'durum--notr',
};

export function Cip({ renk, metin, ikon }: { renk: CipRengi; metin: string; ikon?: string }) {
  return (
    <span className={`cip ${SINIF[renk]}`}>
      {ikon && <span aria-hidden="true">{ikon}</span>}
      {metin}
    </span>
  );
}
