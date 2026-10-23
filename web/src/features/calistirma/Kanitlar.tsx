import { useQuery } from '@tanstack/react-query';

import { kanitBaglantisi, type Kanit } from '../../api/kanitlar';
import { Cip } from '../../bilesenler/Cip';
import { tr } from '../../i18n/tr';

/**
 * Bir maddenin kanıtları: küçük görsel + bayraklar (FR-0615).
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
  const baglanti = useQuery({
    queryKey: ['kanit-baglanti', kanit.id],
    queryFn: () => kanitBaglantisi(kanit.id),
    // Bağlantı 15 dk geçerli; 10 dakikada bir tazeleniyor.
    staleTime: 10 * 60 * 1000,
  });

  return (
    <figure style={{ margin: 0, maxWidth: 160 }}>
      {baglanti.data ? (
        <img
          src={baglanti.data}
          alt={tr.kanit.gorselAlt}
          style={{
            width: 160,
            height: 120,
            objectFit: 'cover',
            borderRadius: 'var(--kose-kart)',
            border: '1px solid var(--renk-cizgi)',
            background: 'var(--renk-yuzey2)',
          }}
        />
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
          {baglanti.isError ? tr.kanit.acilamadi : tr.genel.yukleniyor}
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
