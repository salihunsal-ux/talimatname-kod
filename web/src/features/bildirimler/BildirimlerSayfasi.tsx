import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { bildirimListesi, bildirimSayaclari, type BildirimDurumu } from '../../api/bildirimler';
import { Cip } from '../../bilesenler/Cip';
import { tr } from '../../i18n/tr';
import { Dugme } from '../../bilesenler/Dugme';
import { Hata } from '../../bilesenler/Durum';
import { IskeletTablo } from '../../bilesenler/Iskelet';

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
      <header className="sayfa-basligi">
        <div>
          <h1>{tr.bildirim.baslik}</h1>
          <p className="sayfa-basligi-alt">{tr.bildirim.altBaslik}</p>
        </div>
      </header>

      <div className="yigin">
        {sayac.data && (
          <p
            role="status"
            className={suruculer.length === 0 ? 'bildiri bildiri--uyari' : 'bildiri'}
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

        {sayac.data && (
          <div className="kutu-izgara">
            {(
              [
                ['queued', tr.bildirim.kuyrukta],
                ['sent', tr.bildirim.kanalaVerildi],
                ['failed', tr.bildirim.gonderilemedi],
                ['total', tr.bildirim.toplam],
              ] as const
            ).map(([alan, ad]) => (
              <div key={alan} className="kutu">
                <div className="kutu-ad">{ad}</div>
                <div className="kutu-deger">{sayac.data[alan]}</div>
              </div>
            ))}
          </div>
        )}

        <div className="sekme-serit">
          {SUZGECLER.map(({ anahtar, ad }) => (
            <Dugme
              gorunum="ikincil"
              boyut="kucuk"
              key={anahtar}
              type="button"
              aria-pressed={suzgec === anahtar}
              onClick={() => setSuzgec(anahtar)}
            >
              {ad}
            </Dugme>
          ))}
        </div>

        {liste.isPending && <IskeletTablo sutunlar={4} satirlar={6} />}
        {liste.isError && <Hata metin={tr.hata.aglaBaglanilamadi} />}
        {liste.data?.length === 0 && <p className="bos-durum">{tr.bildirim.bos}</p>}

        {liste.data && liste.data.length > 0 && (
          <div className="tablo-kaydirma">
            <table className="tablo">
              <thead>
                <tr>
                  <th>{tr.bildirim.ne}</th>
                  <th>{tr.bildirim.kime}</th>
                  <th className="sayisal">{tr.bildirim.neZaman}</th>
                  <th>{tr.bildirim.durum}</th>
                </tr>
              </thead>
              <tbody>
                {liste.data.map((bildirim) => (
                  <tr key={bildirim.id}>
                    <th scope="row">
                      {bildirim.title}
                      <div className="meta">
                        {bildirim.kind_label} · {bildirim.channel}
                      </div>
                    </th>
                    <td>{bildirim.user_name}</td>
                    <td className="sayisal">
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
                        <div className="hata-metni">{bildirim.error_code}</div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
