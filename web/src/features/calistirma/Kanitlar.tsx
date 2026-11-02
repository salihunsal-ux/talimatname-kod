import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { kanitBaglantisi, type Kanit } from '../../api/kanitlar';
import { Cip } from '../../bilesenler/Cip';
import { tr } from '../../i18n/tr';
import { Dugme } from '../../bilesenler/Dugme';

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
    <div
      style={{
        width: '100%',
        display: 'flex',
        gap: 'var(--bosluk-3)',
        flexWrap: 'wrap',
        marginTop: 'var(--bosluk-2)',
      }}
    >
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
    <figure style={{ margin: 0, maxWidth: 160 }}>
      {baglanti.data && !acilmadi ? (
        <Dugme
          gorunum="ikincil"
          type="button"
          onClick={tamBoyAc}
          title={kanit.has_stamp ? tr.kanit.damgaliAc : tr.kanit.hamAc}
        >
          <img
            src={baglanti.data}
            alt={tr.kanit.gorselAlt}
            onError={() => setAcilmadi(true)}
            style={{
              width: 160,
              height: 120,
              objectFit: 'cover',
              borderRadius: 'var(--kose-kart)',
              border: '1px solid var(--renk-cizgi)',
              background: 'var(--renk-yuzey2)',
            }}
          />
        </Dugme>
      ) : (
        <div
          style={{
            width: 160,
            height: 120,
            display: 'grid',
            placeItems: 'center',
            borderRadius: 'var(--kose-kart)',
            border: '1px solid var(--renk-cizgi)',
            background: 'var(--renk-yuzey2)',
            color: 'var(--renk-sessiz)',
            fontSize: 'var(--etiket)',
          }}
        >
          {baglanti.isError || acilmadi ? tr.kanit.acilamadi : tr.genel.yukleniyor}
        </div>
      )}

      <figcaption
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 'var(--bosluk-1)',
          marginTop: 'var(--bosluk-1)',
        }}
      >
        {!kanit.has_stamp && (
          <span style={{ fontSize: 'var(--etiket)', color: 'var(--renk-sessiz)' }}>
            {tr.kanit.damgaBekliyor}
          </span>
        )}
        {kanit.flags?.length ? (
          kanit.flags.map((bayrak) => (
            <Cip key={bayrak.code} renk="uyari" ikon="⚑" metin={bayrak.label} />
          ))
        ) : (
          <span style={{ fontSize: 'var(--etiket)', color: 'var(--renk-sessiz)' }}>
            {tr.kanit.bayraksiz}
          </span>
        )}
      </figcaption>
    </figure>
  );
}
