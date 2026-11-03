import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { kanitBaglantisi, type Kanit } from '../../api/kanitlar';
import { Cip } from '../../bilesenler/Cip';
import { tr } from '../../i18n/tr';

/**
 * Bir maddenin kanıtları: küçük görsel + bayraklar (FR-0615).
 *
 * Izgarada **küçük resim** gösterilir (320 px, damgasız); görsele
 * dokunulunca **damgalı kopya** açılır (FR-0606, FR-1202): şube,
 * tarih-saat ve kullanıcı fotoğrafın üstünde yazılı olsun, dışarıya
 * giden dosya bağlamını kendisi taşısın.
 *
 * Bayraklar **kırmızı değil sarı**: suçlama değil, incelemeye çağrı.
 * Renk tek başına anlam taşımadığı için her bayrak metniyle birlikte.
 */
export function Kanitlar({ kanitlar }: { kanitlar: Kanit[] }) {
  if (kanitlar.length === 0) return null;

  return (
    <div className="kanit-serit">
      {kanitlar.map((kanit) => (
        <KanitKarti key={kanit.id} kanit={kanit} />
      ))}
    </div>
  );
}

function KanitKarti({ kanit }: { kanit: Kanit }) {
  // Görsel yüklenemeyebilir: dosya bozuk olabilir, saklama süresi
  // dolmuş olabilir (BR-21). Kırık resim simgesi yerine ne olduğunu
  // yazıyoruz — kullanıcı "kanıt yok" ile "gösterilemiyor"u ayırsın.
  const [acilmadi, setAcilmadi] = useState(false);
  const baglanti = useQuery({
    queryKey: ['kanit-baglanti', kanit.id, 'thumbnail'],
    queryFn: () => kanitBaglantisi(kanit.id, 'thumbnail'),
    // Bağlantı 15 dk geçerli; 10 dakikada bir tazeleniyor.
    staleTime: 10 * 60 * 1000,
  });

  async function tamBoyAc() {
    // Bağlantı **tıklama anında** alınır: 15 dakikalık bir adresi
    // sayfada hazır tutmak, süresini uzatmaya çalışmak olurdu.
    const url = await kanitBaglantisi(kanit.id, kanit.has_stamp ? 'stamped' : 'raw');
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  return (
    <figure className="kanit-cerceve">
      {baglanti.data && !acilmadi ? (
        <button
          type="button"
          className="kanit-dugme"
          onClick={tamBoyAc}
          title={kanit.has_stamp ? tr.kanit.damgaliAc : tr.kanit.hamAc}
        >
          <img
            src={baglanti.data}
            alt={tr.kanit.gorselAlt}
            onError={() => setAcilmadi(true)}
            className="kanit-gorsel"
          />
        </button>
      ) : (
        <div className="kanit-yer">
          {baglanti.isError || acilmadi ? tr.kanit.acilamadi : tr.genel.yukleniyor}
        </div>
      )}

      <figcaption className="kanit-alt">
        {!kanit.has_stamp && <span className="durum-metni">{tr.kanit.damgaBekliyor}</span>}
        {kanit.flags?.length ? (
          kanit.flags.map((bayrak) => (
            <Cip key={bayrak.code} renk="uyari" ikon="⚑" metin={bayrak.label} />
          ))
        ) : (
          <span className="durum-metni">{tr.kanit.bayraksiz}</span>
        )}
      </figcaption>
    </figure>
  );
}
