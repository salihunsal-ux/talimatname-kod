import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import {
  calistirmaIptal,
  calistirmaGorunumu,
  calistirmaPdf,
  type CevapCiktisi,
  type MaddeDurumu,
} from '../../api/calistirma';
import { dosyayiIndir } from '../../api/raporlar';
import { Cip } from '../../bilesenler/Cip';
import { useYonetici } from '../../api/yetki';
import { calistirmaKanitlari, type Kanit } from '../../api/kanitlar';
import { tr } from '../../i18n/tr';
import { Hata, Yukleniyor } from '../../bilesenler/Durum';
import { Kanitlar } from './Kanitlar';
import { Dugme } from '../../bilesenler/Dugme';

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

function tarih(isoGun: string): string {
  return new Date(`${isoGun}T00:00:00`).toLocaleDateString('tr-TR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

/**
 * SCR-W-08 · Çalıştırma detayı: maddeler, cevaplar, puan, eksikler ve
 * **kanıt görselleri** (FR-0606). Görseller imzalı ve 15 dakikalık
 * bağlantıyla geliyor (FR-1305); bayraklar madde altında listeleniyor.
 */
/**
 * Çalıştırma PDF'ini indirir (FR-1213).
 *
 * Kendi durumunu tutuyor: kâğıt sunucuda deriliyor — kanıt küçük
 * resimleri depodan okunuyor — ve bu bir saniyeyi geçebiliyor.
 * Tıklayıp hiçbir şey olmaması kullanıcıyı ikinci kez tıklatır.
 */
function PdfDugmesi({ runId }: { runId: string }) {
  const [durum, setDurum] = useState<'bos' | 'calisiyor' | 'hata'>('bos');

  async function tikla() {
    setDurum('calisiyor');
    try {
      dosyayiIndir(await calistirmaPdf(runId), `talimatname-calistirma-${runId.slice(0, 8)}.pdf`);
      setDurum('bos');
    } catch {
      setDurum('hata');
    }
  }

  return (
    <span className="kart-serit">
      {durum === 'hata' && (
        <span role="alert" className="hata-metni">
          {tr.rapor.pdfHata}
        </span>
      )}
      <Dugme
        type="button"
        onClick={tikla}
        disabled={durum === 'calisiyor'}
        gorunum="ikincil"
        boyut="kucuk"
      >
        {durum === 'calisiyor' ? tr.rapor.pdfHazirlaniyor : tr.rapor.pdfIndir}
      </Dugme>
    </span>
  );
}

/**
 * "Yapılmayacak" (FR-0514, TC-038).
 *
 * Sebep zorunlu ve kutu tıklayınca açılıyor: tek tıkla iptal, yanlış
 * satıra basmayı geri alınamaz hale getirirdi. Geçiş olay günlüğüne
 * sebebiyle yazılıyor.
 */
function YapilmayacakDugmesi({ runId }: { runId: string }) {
  const [acik, setAcik] = useState(false);
  const [sebep, setSebep] = useState('');
  const sorgular = useQueryClient();

  const iptal = useMutation({
    mutationFn: () => calistirmaIptal(runId, sebep),
    onSuccess: () => {
      setAcik(false);
      setSebep('');
      void sorgular.invalidateQueries();
    },
  });

  if (!acik) {
    return (
      <Dugme gorunum="ikincil" boyut="kucuk" type="button" onClick={() => setAcik(true)}>
        {tr.durum.yapilmayacak}
      </Dugme>
    );
  }

  return (
    <form
      onSubmit={(olay) => {
        olay.preventDefault();
        iptal.mutate();
      }}
      className="kart-serit"
    >
      <input
        className="alan alan--genis"
        value={sebep}
        onChange={(o) => setSebep(o.target.value)}
        placeholder={tr.calistirma.yapilmayacakSebep}
        aria-label={tr.calistirma.yapilmayacakSebep}
        required
      />
      <Dugme boyut="kucuk" type="submit" disabled={iptal.isPending || sebep.trim() === ''}>
        {tr.calistirma.yapilmayacakOnay}
      </Dugme>
      <Dugme gorunum="sessiz" boyut="kucuk" type="button" onClick={() => setAcik(false)}>
        {tr.calistirma.yapilmayacakVazgec}
      </Dugme>
      <span className="meta">{tr.calistirma.yapilmayacakNotu}</span>
    </form>
  );
}

//: Listede gösterilen en çok engel. Kalanı sayıyla söyleniyor:
//: başlıkta "(7)" yazıp altta altı satır göstermek, sayan kişiyi
//: kendi gözünden şüphe ettiriyordu.
const ENGEL_GOSTERILEN = 6;

export function CalistirmaDetayi({ runId, onKapat }: { runId: string; onKapat: () => void }) {
  const yonetici = useYonetici();
  const gorunum = useQuery({
    queryKey: ['calistirma', runId],
    queryFn: () => calistirmaGorunumu(runId),
  });
  const kanitlar = useQuery({
    queryKey: ['kanitlar', runId],
    queryFn: () => calistirmaKanitlari(runId),
  });

  if (gorunum.isPending) return <Yukleniyor />;
  if (gorunum.isError || !gorunum.data) return <Hata hata={gorunum.error} />;

  const veri = gorunum.data;

  return (
    <article className="kart">
      {/* Başlıkta şube adı önde: kart panoda ızgaranın altında açılıyor
          ve hangi satıra ait olduğu yalnızca tıklama anında belliydi.
          Liste adı, gün ve pencere altına iniyor — kartı ayıran şey
          "hangi şube", "hangi liste" değil. */}
      <header className="kart-serit">
        <div className="kart-serit-ad">
          <h2 className="baslik-bolum">
            {veri.branch_name}
            {veri.region_name && <span className="baslik-eki"> · {veri.region_name}</span>}
          </h2>
          <p className="meta">
            {veri.template_name} · {tarih(veri.business_day)} · {saat(veri.window_start)}–
            {saat(veri.window_end)}
          </p>
        </div>
        {veri.result && (
          <Cip
            renk={veri.result === 'passed' ? 'marka' : 'kritik'}
            ikon={veri.result === 'passed' ? '✓' : '✕'}
            metin={veri.result === 'passed' ? tr.calistirma.basarili : tr.calistirma.basarisiz}
          />
        )}
        {veri.score_percent !== null && <strong className="sayisal">%{veri.score_percent}</strong>}
        <PdfDugmesi runId={runId} />
        {yonetici && (veri.status === 'scheduled' || veri.status === 'in_progress') && (
          <YapilmayacakDugmesi runId={runId} />
        )}
        <Dugme type="button" onClick={onKapat} gorunum="ikincil" boyut="kucuk">
          {tr.calistirma.kapat}
        </Dugme>
      </header>

      <div className="yigin">
        {veri.blockers.length > 0 && (
          <div role="status" className="bildiri bildiri--uyari">
            <strong>
              {tr.calistirma.eksikler} ({veri.blockers.length})
            </strong>
            <ul className="madde-listesi">
              {veri.blockers.slice(0, ENGEL_GOSTERILEN).map((eksik) => (
                <li key={`${eksik.item_id}-${eksik.kind}`}>
                  {eksik.title} — {tr.calistirma.eksikTuru[eksik.kind]}
                </li>
              ))}
              {veri.blockers.length > ENGEL_GOSTERILEN && (
                <li>{tr.calistirma.dahaFazlaEksik(veri.blockers.length - ENGEL_GOSTERILEN)}</li>
              )}
            </ul>
          </div>
        )}

        {veri.sections.map((bolum) => (
          <section key={bolum.id}>
            <h3 className="bolum-etiketi">{bolum.title}</h3>
            <ul className="sade-liste">
              {bolum.items.map((madde) => (
                <MaddeSatiri
                  key={madde.item_id}
                  madde={madde}
                  // Yalnızca doğrulanmış kanıt gösterilir: "pending" bir
                  // niyet beyanıdır, baytları henüz depoda değil (ST-054).
                  kanitlar={(kanitlar.data ?? []).filter(
                    (k) => k.item_id === madde.item_id && k.status !== 'pending',
                  )}
                />
              ))}
            </ul>
          </section>
        ))}
      </div>
    </article>
  );
}

/**
 * Cevabın **değeri**: kaç derece ölçüldü, hangi seçenek seçildi, vardiya
 * notu ne diyordu. Satır yalnızca "Geçti/Geçmedi" yazıyordu; denetleyen
 * kişi ölçümü bu ekrandan hiç göremiyordu (bağımsız test turu B07).
 * Veri uç noktada zaten vardı, basılmıyordu.
 */
function Deger({ madde, cevap }: { madde: MaddeDurumu; cevap: CevapCiktisi }) {
  if (cevap.value == null) return null;
  if (madde.type === 'temperature' || madde.type === 'number') {
    return (
      <strong className="madde-satiri-deger">
        {String(cevap.value)}
        {madde.unit ? ` ${madde.unit}` : ''}
      </strong>
    );
  }
  if (madde.type === 'choice') return <Cip renk="nötr" metin={String(cevap.value)} />;
  // Metin cevabı değerde duruyor (notta değil): kendi satırına iner.
  if (madde.type === 'text') return <span className="madde-satiri-not">{String(cevap.value)}</span>;
  return null;
}

function MaddeSatiri({ madde, kanitlar }: { madde: MaddeDurumu; kanitlar: Kanit[] }) {
  const cevap = madde.answer;
  const gorunum = cevap ? CEVAP[cevap.state] : null;
  const talimat = madde.type === 'instruction';

  return (
    <li className={talimat ? 'madde-satiri madde-satiri--talimat' : 'madde-satiri'}>
      <span className="madde-satiri-ad">
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
          {cevap && <Deger madde={madde} cevap={cevap} />}
          <Cip renk={gorunum.renk} ikon={gorunum.ikon} metin={gorunum.ad} />
          {cevap?.not_done_reason_label && <Cip renk="uyari" metin={cevap.not_done_reason_label} />}
          {cevap?.evidence_count ? (
            <Cip renk="nötr" ikon="📷" metin={`${cevap.evidence_count}`} />
          ) : null}
          <Kanitlar kanitlar={kanitlar} />
          {cevap?.clock_flagged && <Cip renk="uyari" ikon="⏱" metin={tr.calistirma.saatSapmasi} />}
          {cevap?.note && <span className="madde-satiri-not">{cevap.note}</span>}
          {cevap && (cevap.answered_by || cevap.answered_at) && (
            <span className="madde-satiri-kim">
              {[cevap.answered_by, saat(cevap.answered_at)].filter(Boolean).join(' · ')}
            </span>
          )}
        </>
      ) : (
        <Cip renk="pasif" ikon="○" metin={tr.calistirma.cevapsiz} />
      )}
    </li>
  );
}
