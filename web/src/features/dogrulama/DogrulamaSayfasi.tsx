import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { problemCoz } from '../../api/client';
import { belgeDogrula, type DogrulamaSonucu } from '../../api/dogrulama';
import { Dugme } from '../../bilesenler/Dugme';
import { Kart } from '../../bilesenler/Kart';
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
    <main className="orta-sayfa">
      <Kart yuzen aria-labelledby="dogrulama-baslik" style={{ width: '100%', maxWidth: 440 }}>
        <h1 id="dogrulama-baslik" className="baslik-ekran">
          {tr.dogrulama.baslik}
        </h1>
        <p className="meta" style={{ margin: 'var(--bosluk-1) 0 var(--bosluk-4)' }}>
          {tr.dogrulama.aciklama}
        </p>

        <form
          onSubmit={(olay) => {
            olay.preventDefault();
            setSorulan(kod.trim());
          }}
        >
          <label htmlFor="belge-kodu" className="alan-etiket">
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
            className="alan"
            style={{ letterSpacing: '0.12em', textTransform: 'uppercase' }}
          />
          <Dugme
            type="submit"
            tam
            disabled={sonuc.isFetching}
            style={{ marginTop: 'var(--bosluk-3)' }}
          >
            {sonuc.isFetching ? tr.genel.yukleniyor : tr.dogrulama.sor}
          </Dugme>
        </form>

        {sonuc.isError && (
          <p
            role="alert"
            className="bildiri bildiri--hata"
            style={{ marginTop: 'var(--bosluk-3)' }}
          >
            {hataMetni(sonuc.error)}
          </p>
        )}

        {sonuc.data !== undefined && !sonuc.isError && <Kayit kayit={sonuc.data} />}

        <p className="dipnot">{tr.dogrulama.sinir}</p>
        <a href="/" className="meta" style={{ color: 'var(--renk-marka)' }}>
          {tr.dogrulama.panele}
        </a>
      </Kart>
    </main>
  );
}

function Kayit({ kayit }: { kayit: DogrulamaSonucu }) {
  const saglam = kayit.record_intact && kayit.chain_linked;
  return (
    <div style={{ marginTop: 'var(--bosluk-4)' }}>
      <p
        role="status"
        className={saglam ? 'bildiri bildiri--saglam' : 'bildiri bildiri--uyari'}
        style={{ margin: 0 }}
      >
        {saglam ? tr.dogrulama.saglam : tr.dogrulama.kirik}
      </p>

      <dl className="veri-liste">
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

      <p className="dipnot">{tr.dogrulama.karsilastir}</p>
    </div>
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
