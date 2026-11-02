import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { bildirimListesi, bildirimSayaclari, type BildirimDurumu } from '../../api/bildirimler';
import { Cip } from '../../bilesenler/Cip';
import { tr } from '../../i18n/tr';

const SUZGECLER: { anahtar: BildirimDurumu; ad: string }[] = [
  { anahtar: 'all', ad: tr.bildirim.hepsi },
  { anahtar: 'queued', ad: tr.bildirim.kuyrukta },
  { anahtar: 'failed', ad: tr.bildirim.gonderilemedi },
  { anahtar: 'sent', ad: tr.bildirim.kanalaVerildi },
];

const DURUM_RENGI: Record<string, 'marka' | 'kritik' | 'uyari' | 'pasif'> = {
  delivered: 'marka',
  sent: 'uyari',
  queued: 'pasif',
  failed: 'kritik',
  suppressed: 'pasif',
};

/**
 * SCR-W-11 · Teslimat izi (FR-1005): bildirim gitti mi, gitmediyse neden.
 *
 * Sayfanın işi rahatlatmak değil, **göstermek**. Sürücü bağlı değilken
 * kayıtlar "gönderilemedi / surucu-yok" görünür; bu bir hata ekranı
 * değil, eksik entegrasyonun listesidir.
 */
export function BildirimlerSayfasi() {
  const [suzgec, setSuzgec] = useState<BildirimDurumu>('all');
  const sayac = useQuery({ queryKey: ['bildirim-sayac'], queryFn: bildirimSayaclari });
  const liste = useQuery({
    queryKey: ['bildirimler', suzgec],
    queryFn: () => bildirimListesi(suzgec),
  });

  const suruculer = sayac.data?.drivers_connected ?? [];

  return (
    <div>
      <h1 style={{ fontSize: 'var(--baslik-ekran)', margin: '0 0 var(--bosluk-3)' }}>
        {tr.bildirim.baslik}
      </h1>

      {sayac.data && (
        <p
          role="status"
          style={{
            background: suruculer.length === 0 ? 'var(--renk-uyari-acik)' : 'var(--renk-yuzey2)',
            border: '1px solid var(--renk-cizgi)',
            borderRadius: 'var(--kose-kart)',
            padding: 'var(--bosluk-3)',
            fontSize: 'var(--etiket)',
            color: 'var(--renk-murekkep)',
            margin: '0 0 var(--bosluk-4)',
          }}
        >
          {suruculer.length === 0 ? (
            <>
              <strong>{tr.bildirim.surucuYok}</strong> {tr.bildirim.surucuYokAciklama}
            </>
          ) : (
            <>
              {tr.bildirim.bagliKanallar} <strong>{suruculer.join(', ')}</strong>
            </>
          )}
        </p>
      )}

      <div
        style={{
          display: 'flex',
          gap: 'var(--bosluk-4)',
          flexWrap: 'wrap',
          margin: '0 0 var(--bosluk-4)',
        }}
      >
        {sayac.data &&
          (
            [
              ['queued', tr.bildirim.kuyrukta],
              ['sent', tr.bildirim.kanalaVerildi],
              ['failed', tr.bildirim.gonderilemedi],
              ['total', tr.bildirim.toplam],
            ] as const
          ).map(([alan, ad]) => (
            <div key={alan}>
              <div style={{ fontSize: 'var(--etiket)', color: 'var(--renk-sessiz)' }}>{ad}</div>
              <div style={{ fontSize: 'var(--baslik-bolum)', fontVariantNumeric: 'tabular-nums' }}>
                {sayac.data[alan]}
              </div>
            </div>
          ))}
      </div>

      <div style={{ display: 'flex', gap: 'var(--bosluk-2)', marginBottom: 'var(--bosluk-3)' }}>
        {SUZGECLER.map(({ anahtar, ad }) => (
          <button
            key={anahtar}
            type="button"
            aria-pressed={suzgec === anahtar}
            onClick={() => setSuzgec(anahtar)}
            style={{
              minHeight: 36,
              padding: '0 var(--bosluk-3)',
              border: '1px solid',
              borderColor: suzgec === anahtar ? 'var(--renk-marka)' : 'var(--renk-cizgi)',
              borderRadius: 'var(--kose-dugme)',
              background: suzgec === anahtar ? 'var(--renk-marka-acik)' : 'transparent',
              color: 'var(--renk-murekkep)',
              cursor: 'pointer',
            }}
          >
            {ad}
          </button>
        ))}
      </div>

      {liste.isPending && <p style={{ color: 'var(--renk-sessiz)' }}>{tr.genel.yukleniyor}</p>}
      {liste.isError && (
        <p role="alert" style={{ color: 'var(--renk-kritik)' }}>
          {tr.hata.aglaBaglanilamadi}
        </p>
      )}
      {liste.data?.length === 0 && <p style={{ color: 'var(--renk-sessiz)' }}>{tr.bildirim.bos}</p>}

      {liste.data && liste.data.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--govde)' }}>
          <thead>
            <tr
              style={{ textAlign: 'left', color: 'var(--renk-sessiz)', fontSize: 'var(--etiket)' }}
            >
              <th style={{ padding: '6px 0' }}>{tr.bildirim.ne}</th>
              <th>{tr.bildirim.kime}</th>
              <th>{tr.bildirim.neZaman}</th>
              <th>{tr.bildirim.durum}</th>
            </tr>
          </thead>
          <tbody>
            {liste.data.map((bildirim) => (
              <tr key={bildirim.id} style={{ borderTop: '1px solid var(--renk-cizgi)' }}>
                <td style={{ padding: '10px 0' }}>
                  {bildirim.title}
                  <div style={{ fontSize: 'var(--etiket)', color: 'var(--renk-sessiz)' }}>
                    {bildirim.kind_label} · {bildirim.channel}
                  </div>
                </td>
                <td style={{ color: 'var(--renk-murekkep2)' }}>{bildirim.user_name}</td>
                <td
                  style={{
                    fontVariantNumeric: 'tabular-nums',
                    color: 'var(--renk-murekkep2)',
                    fontSize: 'var(--etiket)',
                  }}
                >
                  {new Date(bildirim.send_at).toLocaleString('tr-TR', {
                    day: '2-digit',
                    month: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </td>
                <td>
                  <Cip
                    renk={DURUM_RENGI[bildirim.status ?? 'queued'] ?? 'pasif'}
                    ikon={bildirim.status === 'failed' ? '✕' : '•'}
                    metin={bildirim.status_label}
                  />
                  {bildirim.error_code && (
                    <div style={{ fontSize: 'var(--etiket)', color: 'var(--renk-kritik)' }}>
                      {bildirim.error_code}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
