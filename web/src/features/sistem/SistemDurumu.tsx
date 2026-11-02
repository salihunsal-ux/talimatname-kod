import { useQuery } from '@tanstack/react-query';

import { sistemDurumuGetir } from '../../api/sistem';
import { tr } from '../../i18n/tr';
import { Cip } from '../../bilesenler/Cip';

/**
 * İlk uçtan uca dilim: üretilmiş istemciyle /health çağrısı, üç durum
 * (yükleniyor · hata · veri) ve token'larla biçim. Panelin geri kalanı
 * bu desenin üstüne gelecek.
 */
export function SistemDurumu() {
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ['sistem-durumu'],
    queryFn: sistemDurumuGetir,
  });

  return (
    <section
      aria-labelledby="sistem-baslik"
      style={{
        background: 'var(--renk-yuzey)',
        border: '1px solid var(--renk-cizgi)',
        borderRadius: 'var(--kose-kart)',
        padding: 'var(--bosluk-4)',
        maxWidth: 520,
      }}
    >
      <h1 id="sistem-baslik" style={{ fontSize: 'var(--baslik-ekran)', margin: 0 }}>
        {tr.sistem.baslik}
      </h1>

      {isPending && (
        <p style={{ color: 'var(--renk-sessiz)' }} role="status">
          {tr.sistem.yukleniyor}
        </p>
      )}

      {isError && (
        <div role="alert" style={{ marginTop: 'var(--bosluk-3)' }}>
          <Cip renk="kritik" ikon="✕" metin={tr.sistem.ulasilamiyor} />
          <p style={{ color: 'var(--renk-murekkep2)' }}>{tr.hata.aglaBaglanilamadi}</p>
          <button
            type="button"
            onClick={() => void refetch()}
            style={{
              padding: '0 var(--bosluk-4)',
              borderRadius: 'var(--kose-dugme)',
              border: '1px solid var(--renk-cizgi)',
              background: 'var(--renk-yuzey2)',
              color: 'var(--renk-murekkep)',
              cursor: 'pointer',
            }}
          >
            {tr.sistem.yenile}
          </button>
        </div>
      )}

      {data && (
        <div style={{ marginTop: 'var(--bosluk-3)' }}>
          <Cip renk="marka" ikon="✓" metin={tr.sistem.saglikli} />
          <dl
            style={{
              display: 'grid',
              gridTemplateColumns: 'auto 1fr',
              gap: 'var(--bosluk-2) var(--bosluk-4)',
              margin: 'var(--bosluk-3) 0 0',
            }}
          >
            <Satir ad={tr.sistem.surum} deger={data.version} />
            <Satir ad={tr.sistem.ortam} deger={data.environment} />
            <Satir
              ad={tr.sistem.veritabani}
              deger={
                data.database_configured ? tr.sistem.yapilandirilmis : tr.sistem.yapilandirilmamis
              }
            />
            <Satir
              ad={tr.sistem.nesneDepo}
              deger={
                data.object_store_configured
                  ? tr.sistem.yapilandirilmis
                  : tr.sistem.yapilandirilmamis
              }
            />
            {/* Demo modu açıkken doğrulama kodu yanıtta görünüyor, yani
                giriş tek faktöre iniyor. Bunu ekranda söylemek şart:
                kapalı sanılan bir kapı, açık kapıdan tehlikeli. */}
            <Satir
              ad={tr.sistem.demoKod}
              deger={data.demo_show_otp_code ? tr.sistem.demoKodAcik : tr.sistem.demoKodKapali}
            />
            {/* Kapalıyken sessizce "güvenli" demiyoruz: zincirin neyi
                gösterip neyi göstermediği burada yazılı (FR-1302). */}
            <Satir
              ad={tr.sistem.cipalama}
              deger={data.timestamping_configured ? tr.sistem.acik : tr.sistem.kapali}
            />
          </dl>
        </div>
      )}
    </section>
  );
}

function Satir({ ad, deger }: { ad: string; deger: string }) {
  return (
    <>
      <dt style={{ color: 'var(--renk-sessiz)', fontSize: 'var(--etiket)' }}>{ad}</dt>
      <dd style={{ margin: 0, fontVariantNumeric: 'tabular-nums' }}>{deger}</dd>
    </>
  );
}
