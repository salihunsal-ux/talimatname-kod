/**
 * Durum çipi (tasarım sistemi · "Durum çipi"): renk tek başına anlam
 * taşımaz, ikon + metin birlikte verilir (NFR-11).
 */
export type CipRengi = 'marka' | 'kritik' | 'uyari' | 'pasif' | 'nötr';

const RENKLER: Record<CipRengi, { zemin: string; yazi: string }> = {
  marka: { zemin: 'var(--renk-marka-acik)', yazi: 'var(--renk-marka)' },
  kritik: { zemin: 'var(--renk-kritik-acik)', yazi: 'var(--renk-kritik)' },
  uyari: { zemin: 'var(--renk-uyari-acik)', yazi: 'var(--renk-uyari)' },
  pasif: { zemin: 'var(--renk-yuzey2)', yazi: 'var(--renk-sessiz)' },
  nötr: { zemin: 'var(--renk-yuzey2)', yazi: 'var(--renk-murekkep2)' },
};

export function Cip({ renk, metin, ikon }: { renk: CipRengi; metin: string; ikon?: string }) {
  const { zemin, yazi } = RENKLER[renk];
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--bosluk-1)',
        padding: '2px var(--bosluk-3)',
        borderRadius: 'var(--kose-cip)',
        fontSize: 'var(--etiket)',
        fontWeight: 600,
        background: zemin,
        color: yazi,
        whiteSpace: 'nowrap',
      }}
    >
      {ikon && <span aria-hidden="true">{ikon}</span>}
      {metin}
    </span>
  );
}
