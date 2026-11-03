import { useQuery } from '@tanstack/react-query';

import { sistemDurumuGetir } from '../../api/sistem';
import { tr } from '../../i18n/tr';
import { Cip } from '../../bilesenler/Cip';
import { Dugme } from '../../bilesenler/Dugme';
import { Yukleniyor } from '../../bilesenler/Durum';

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
    <section className="kart dar-kart" aria-labelledby="sistem-baslik">
      <h1 id="sistem-baslik" className="baslik-ekran">
        {tr.sistem.baslik}
      </h1>

      {isPending && <Yukleniyor metin={tr.sistem.yukleniyor} />}

      {isError && (
        <div role="alert" className="yigin yigin--dar">
          <div className="cip-listesi">
            <Cip renk="kritik" ikon="✕" metin={tr.sistem.ulasilamiyor} />
          </div>
          <p>{tr.hata.aglaBaglanilamadi}</p>
          <div className="eylemler">
            <Dugme gorunum="ikincil" type="button" onClick={() => void refetch()}>
              {tr.sistem.yenile}
            </Dugme>
          </div>
        </div>
      )}

      {data && (
        <div className="yigin yigin--dar">
          <div className="cip-listesi">
            <Cip renk="marka" ikon="✓" metin={tr.sistem.saglikli} />
          </div>
          <dl className="veri-liste">
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
      <dt>{ad}</dt>
      <dd>{deger}</dd>
    </>
  );
}
