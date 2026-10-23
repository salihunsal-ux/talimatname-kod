import { useQuery } from '@tanstack/react-query';

import { calistirmaGorunumu, type MaddeDurumu } from '../../api/calistirma';
import { Cip } from '../../bilesenler/Cip';
import { tr } from '../../i18n/tr';

const CEVAP: Record<
  string,
  { renk: 'marka' | 'kritik' | 'uyari' | 'pasif'; ikon: string; ad: string }
> = {
  passed: { renk: 'marka', ikon: '✓', ad: tr.calistirma.gecti },
  failed: { renk: 'kritik', ikon: '✕', ad: tr.calistirma.gecmedi },
  not_done: { renk: 'uyari', ikon: '!', ad: tr.calistirma.yapilamadi },
  not_applicable: { renk: 'pasif', ikon: '–', ad: tr.calistirma.uygunDegil },
};

function saat(iso: string | null | undefined): string {
  return iso
    ? new Date(iso).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })
    : '';
}

/**
 * SCR-W-08 · Çalıştırma detayı (v1 alt kümesi): maddeler, cevaplar, puan
 * ve eksikler. Kanıt dosyaları Faz B'de (mobil kamera) geliyor; burada
 * şimdilik **kanıt sayısı** gösteriliyor, uydurma görsel değil.
 */
export function CalistirmaDetayi({ runId, onKapat }: { runId: string; onKapat: () => void }) {
  const gorunum = useQuery({
    queryKey: ['calistirma', runId],
    queryFn: () => calistirmaGorunumu(runId),
  });

  if (gorunum.isPending)
    return <p style={{ color: 'var(--renk-sessiz)' }}>{tr.genel.yukleniyor}</p>;
  if (gorunum.isError || !gorunum.data)
    return (
      <p role="alert" style={{ color: 'var(--renk-kritik)' }}>
        {tr.hata.genel}
      </p>
    );

  const veri = gorunum.data;

  return (
    <article
      style={{
        background: 'var(--renk-yuzey)',
        border: '1px solid var(--renk-cizgi)',
        borderRadius: 'var(--kose-kart)',
        padding: 'var(--bosluk-4)',
      }}
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 'var(--bosluk-3)',
          flexWrap: 'wrap',
        }}
      >
        <h2 style={{ fontSize: 'var(--baslik-bolum)', margin: 0 }}>{veri.template_name}</h2>
        <span style={{ color: 'var(--renk-sessiz)', fontSize: 'var(--etiket)' }}>
          {veri.business_day} · {saat(veri.window_start)}–{saat(veri.window_end)}
        </span>
        {veri.result && (
          <Cip
            renk={veri.result === 'passed' ? 'marka' : 'kritik'}
            ikon={veri.result === 'passed' ? '✓' : '✕'}
            metin={veri.result === 'passed' ? tr.calistirma.basarili : tr.calistirma.basarisiz}
          />
        )}
        {veri.score_percent !== null && (
          <strong style={{ fontVariantNumeric: 'tabular-nums' }}>%{veri.score_percent}</strong>
        )}
        <button type="button" onClick={onKapat} style={{ ...kucukDugme, marginLeft: 'auto' }}>
          {tr.calistirma.kapat}
        </button>
      </header>

      {veri.blockers.length > 0 && (
        <div
          role="status"
          style={{
            marginTop: 'var(--bosluk-3)',
            background: 'var(--renk-uyari-acik)',
            borderRadius: 'var(--kose-dugme)',
            padding: 'var(--bosluk-3)',
            fontSize: 'var(--etiket)',
          }}
        >
          <strong>
            {tr.calistirma.eksikler} ({veri.blockers.length})
          </strong>
          <ul style={{ margin: 'var(--bosluk-2) 0 0', paddingLeft: 'var(--bosluk-4)' }}>
            {veri.blockers.slice(0, 6).map((eksik) => (
              <li key={`${eksik.item_id}-${eksik.kind}`}>
                {eksik.title} — {tr.calistirma.eksikTuru[eksik.kind]}
              </li>
            ))}
          </ul>
        </div>
      )}

      {veri.sections.map((bolum) => (
        <section key={bolum.id} style={{ marginTop: 'var(--bosluk-4)' }}>
          <h3
            style={{
              fontSize: 'var(--etiket)',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: 'var(--renk-sessiz)',
              margin: '0 0 var(--bosluk-2)',
            }}
          >
            {bolum.title}
          </h3>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {bolum.items.map((madde) => (
              <MaddeSatiri key={madde.item_id} madde={madde} />
            ))}
          </ul>
        </section>
      ))}
    </article>
  );
}

function MaddeSatiri({ madde }: { madde: MaddeDurumu }) {
  const cevap = madde.answer;
  const gorunum = cevap ? CEVAP[cevap.state] : null;
  const talimat = madde.type === 'instruction';

  return (
    <li
      style={{
        display: 'flex',
        gap: 'var(--bosluk-2)',
        alignItems: 'center',
        flexWrap: 'wrap',
        padding: 'var(--bosluk-2) 0',
        borderTop: '1px solid var(--renk-cizgi)',
        color: talimat ? 'var(--renk-murekkep2)' : undefined,
      }}
    >
      <span style={{ flex: '1 1 240px' }}>
        {madde.title}
        {madde.critical && (
          <>
            {' '}
            <Cip renk="kritik" ikon="!" metin={tr.sablon.kritik} />
          </>
        )}
      </span>

      {talimat ? (
        <Cip renk="nötr" metin={madde.type_label} />
      ) : gorunum ? (
        <>
          <Cip renk={gorunum.renk} ikon={gorunum.ikon} metin={gorunum.ad} />
          {cevap?.evidence_count ? (
            <Cip renk="nötr" ikon="📷" metin={`${cevap.evidence_count}`} />
          ) : null}
          {cevap?.clock_flagged && <Cip renk="uyari" ikon="⏱" metin={tr.calistirma.saatSapmasi} />}
          {cevap?.note && (
            <span
              style={{ width: '100%', color: 'var(--renk-murekkep2)', fontSize: 'var(--etiket)' }}
            >
              {cevap.note}
            </span>
          )}
        </>
      ) : (
        <Cip renk="pasif" ikon="○" metin={tr.calistirma.cevapsiz} />
      )}
    </li>
  );
}

const kucukDugme = {
  padding: '0 var(--bosluk-3)',
  minHeight: 32,
  borderRadius: 'var(--kose-dugme)',
  border: '1px solid var(--renk-cizgi)',
  background: 'var(--renk-yuzey2)',
  color: 'var(--renk-murekkep)',
  cursor: 'pointer',
  fontSize: 'var(--etiket)',
} as const;
