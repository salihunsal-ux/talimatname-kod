import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { problemCoz } from '../../api/client';
import { belgeDogrula, type DogrulamaSonucu } from '../../api/dogrulama';
import { tr } from '../../i18n/tr';

/**
 * Belge doğrulama: kâğıttaki koddan kayda (ST-101; FR-1218).
 *
 * **Oturumsuz** sayfa: denetçi ya da müşteri bir kullanıcı değil,
 * panele giremez. Doğrulanamayan bir belge kodu, kâğıdın üstündeki
 * güvenceyi süs hâline getirirdi.
 *
 * Sayfa, kâğıtta **zaten yazılı olan** alanları gösteriyor (tür,
 * dönem, şube kodu, üretim zamanı); karşılaştırmayı insan yapıyor.
 * Puan, madde sonuçları ve kimin ürettiği gösterilmiyor: kodu eline
 * geçiren herkese şirketin iç verisini açmak olurdu.
 */
export function DogrulamaSayfasi({ kod: ilkKod }: { kod: string }) {
  const [kod, setKod] = useState(ilkKod);
  const [sorulan, setSorulan] = useState(ilkKod.trim());

  const sonuc = useQuery({
    queryKey: ['belge', sorulan],
    queryFn: () => belgeDogrula(sorulan),
    enabled: sorulan !== '',
    retry: false,
  });

  return (
    <main style={sayfa}>
      <section aria-labelledby="dogrulama-baslik" style={kart}>
        <h1 id="dogrulama-baslik" style={{ fontSize: 'var(--baslik-ekran)', margin: 0 }}>
          {tr.dogrulama.baslik}
        </h1>
        <p style={{ color: 'var(--renk-sessiz)', fontSize: 'var(--meta)', marginTop: 4 }}>
          {tr.dogrulama.aciklama}
        </p>

        <form
          onSubmit={(olay) => {
            olay.preventDefault();
            setSorulan(kod.trim());
          }}
        >
          <label htmlFor="belge-kodu" style={etiket}>
            {tr.dogrulama.kod}
          </label>
          <input
            id="belge-kodu"
            name="kod"
            required
            value={kod}
            onChange={(olay) => setKod(olay.target.value)}
            placeholder={tr.dogrulama.kodOrnek}
            autoCapitalize="characters"
            spellCheck={false}
            style={{ ...alan, letterSpacing: '0.12em', textTransform: 'uppercase' }}
          />
          <button type="submit" disabled={sonuc.isFetching} style={dugme}>
            {sonuc.isFetching ? tr.genel.yukleniyor : tr.dogrulama.sor}
          </button>
        </form>

        {sonuc.isError && (
          <p role="alert" style={{ ...kutu, borderColor: 'var(--renk-kritik)' }}>
            {hataMetni(sonuc.error)}
          </p>
        )}

        {sonuc.data !== undefined && !sonuc.isError && <Kayit kayit={sonuc.data} />}

        <p style={{ ...dipnot, marginTop: 'var(--bosluk-4)' }}>{tr.dogrulama.sinir}</p>
        <a href="/" style={{ fontSize: 'var(--meta)', color: 'var(--renk-marka)' }}>
          {tr.dogrulama.panele}
        </a>
      </section>
    </main>
  );
}

function Kayit({ kayit }: { kayit: DogrulamaSonucu }) {
  const saglam = kayit.record_intact && kayit.chain_linked;
  return (
    <div style={{ marginTop: 'var(--bosluk-4)' }}>
      <p
        role="status"
        style={{
          ...kutu,
          background: saglam ? 'var(--renk-marka-acik)' : 'var(--renk-uyari-acik)',
          borderColor: saglam ? 'var(--renk-marka)' : 'var(--renk-uyari)',
          color: 'var(--renk-murekkep)',
        }}
      >
        {saglam ? tr.dogrulama.saglam : tr.dogrulama.kirik}
      </p>

      <dl style={liste}>
        <Satir ad={tr.dogrulama.kod} deger={kayit.code} />
        <Satir ad={tr.dogrulama.tur} deger={kayit.document_label} />
        {kayit.period !== null && kayit.period !== undefined && (
          <Satir ad={tr.dogrulama.donem} deger={kayit.period} />
        )}
        {kayit.branch_code !== null && kayit.branch_code !== undefined && (
          <Satir ad={tr.dogrulama.sube} deger={kayit.branch_code} />
        )}
        <Satir ad={tr.dogrulama.uretim} deger={zaman(kayit.issued_at, kayit.timezone)} />
        <Satir
          ad={tr.dogrulama.kayitOzeti}
          deger={kayit.record_intact ? tr.dogrulama.tutuyor : tr.dogrulama.tutmuyor}
        />
        <Satir
          ad={tr.dogrulama.zincirBagi}
          deger={kayit.chain_linked ? tr.dogrulama.tutuyor : tr.dogrulama.tutmuyor}
        />
      </dl>

      <p style={dipnot}>{tr.dogrulama.karsilastir}</p>
    </div>
  );
}

function Satir({ ad, deger }: { ad: string; deger: string }) {
  return (
    <>
      <dt style={{ color: 'var(--renk-murekkep2)', fontSize: 'var(--meta)' }}>{ad}</dt>
      <dd style={{ margin: 0, fontVariantNumeric: 'tabular-nums' }}>{deger}</dd>
    </>
  );
}

/**
 * Kâğıtta **yerel** saat yazılı: hesabın saat dilimi sunucudan geliyor.
 * UTC göstermek, denetçiye iki farklı saat göstermek olurdu.
 */
function zaman(iso: string, saatDilimi: string): string {
  const an = new Date(iso);
  try {
    return new Intl.DateTimeFormat('tr-TR', {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: saatDilimi,
    }).format(an);
  } catch {
    // Bilinmeyen saat dilimi adı: saati hiç göstermemek yerine
    // tarayıcının dilimiyle gösteriyoruz.
    return an.toLocaleString('tr-TR');
  }
}

/** Davranış `type` alanına bağlı; Türkçe başlık değişebilir (ADR-0014 md.8). */
function hataMetni(sebep: unknown): string {
  const problem = problemCoz(sebep);
  if (problem === null) return tr.hata.aglaBaglanilamadi;
  switch (problem.type) {
    case 'urn:talimatname:belge-bulunamadi':
      return tr.dogrulama.bulunamadi;
    case 'urn:talimatname:gecersiz-istek':
      return tr.dogrulama.gecersiz;
    case 'urn:talimatname:cok-fazla-deneme':
      return tr.dogrulama.cokDeneme;
    case 'urn:talimatname:belge-kodu-benzersiz-degil':
      return tr.dogrulama.benzersizDegil;
    default:
      return problem.detail ?? problem.title;
  }
}

const sayfa = {
  minHeight: '100vh',
  display: 'grid',
  placeItems: 'center',
  padding: 'var(--bosluk-4)',
} as const;

const kart = {
  background: 'var(--renk-yuzey)',
  border: '1px solid var(--renk-cizgi)',
  borderRadius: 'var(--kose-kart)',
  padding: 'var(--bosluk-4)',
  width: '100%',
  maxWidth: 440,
} as const;

const etiket = {
  display: 'block',
  marginTop: 'var(--bosluk-4)',
  fontSize: 'var(--meta)',
  color: 'var(--renk-murekkep2)',
} as const;

const alan = {
  width: '100%',
  minHeight: 44,
  marginTop: 4,
  padding: '0 var(--bosluk-3)',
  border: '1px solid var(--renk-cizgi)',
  borderRadius: 'var(--kose-dugme)',
  background: 'var(--renk-zemin)',
  color: 'var(--renk-murekkep)',
  boxSizing: 'border-box',
} as const;

const dugme = {
  width: '100%',
  minHeight: 44,
  marginTop: 'var(--bosluk-3)',
  border: '1px solid var(--renk-marka)',
  borderRadius: 'var(--kose-dugme)',
  background: 'var(--renk-marka)',
  color: '#fff',
  cursor: 'pointer',
} as const;

const kutu = {
  marginTop: 'var(--bosluk-3)',
  padding: 'var(--bosluk-2) var(--bosluk-3)',
  border: '1px solid var(--renk-cizgi)',
  borderRadius: 'var(--kose-kart)',
  fontSize: 'var(--meta)',
} as const;

const liste = {
  display: 'grid',
  gridTemplateColumns: 'auto 1fr',
  columnGap: 'var(--bosluk-4)',
  rowGap: 6,
  alignItems: 'baseline',
  margin: 'var(--bosluk-3) 0 0',
} as const;

const dipnot = {
  marginTop: 'var(--bosluk-3)',
  color: 'var(--renk-sessiz)',
  fontSize: 'var(--meta)',
} as const;
