import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { problemCoz } from '../../api/client';
import { calistirmaGorunumu, type MaddeDurumu } from '../../api/calistirma';
import { gununCalistirmalari } from '../../api/planlar';
import { cevapYaz, kanitYukle, listeyiGonder, senkManifesti, surumDetayi } from '../../api/saha';
import { Cip } from '../../bilesenler/Cip';
import { Dugme } from '../../bilesenler/Dugme';
import { Hata, Yukleniyor } from '../../bilesenler/Durum';
import { IskeletListe } from '../../bilesenler/Iskelet';
import { tr } from '../../i18n/tr';

/**
 * Saha istemcisi — telefonda çalışan demo (SCR-M-03, SCR-M-04).
 *
 * Mobil uygulamanın bağlanacağı **aynı** uç noktaları kullanıyor:
 * cevap kimliği cihazda üretiliyor, kanıt üç adımda yükleniyor.
 * Amacı iki tane: demo panosunu gerçek veriyle doldurmak ve
 * sözleşmeyi gerçek bir istemciyle sınamak.
 *
 * **Olmayanlar, bilerek:** çevrimdışı kuyruk (Spike A) ve kamera
 * bütünlüğü (Spike C). Tarayıcı "yalnızca kamera"yı garanti edemediği
 * için her fotoğraf `galeri` bayrağıyla yazılıyor — demo yalan
 * söylemesin, bayrak doğruyu söylesin.
 */
export function SahaSayfasi() {
  const [acik, setAcik] = useState<string | null>(null);

  return (
    <div className="yigin">
      <p className="bildiri bildiri--uyari">{tr.saha.demoBandi}</p>
      {acik === null ? (
        <BugunListesi onAc={setAcik} />
      ) : (
        <ListeCalistirma runId={acik} onKapat={() => setAcik(null)} />
      )}
      <Eksikler />
    </div>
  );
}

/**
 * Eksikler listesi ekranın içinde duruyor, belgede değil: bu istemciyi
 * gören herkes neyin olmadığını da görsün. İki grup ayrı, çünkü
 * "tarayıcı yapamıyor" ile "yazılmadı" farklı kararlar doğuruyor.
 */
function Eksikler() {
  const { eksikler } = tr.saha;
  const toplam = eksikler.tarayiciYapamaz.length + eksikler.yazilmadiListe.length;

  return (
    <details className="eksikler">
      <summary>
        {eksikler.baslik} ({toplam})
      </summary>
      <div className="yigin yigin--dar">
        <p className="ikincil-metin">{eksikler.aciklama}</p>
        {(
          [
            [eksikler.yapilamaz, eksikler.tarayiciYapamaz, 'kritik'],
            [eksikler.yazilmadi, eksikler.yazilmadiListe, 'uyari'],
          ] as const
        ).map(([baslik, liste, renk]) => (
          <section key={baslik}>
            <h2 className="bolum-etiketi">{baslik}</h2>
            <ul className="liste-yigin">
              {liste.map(([gereksinim, metin]) => (
                <li key={gereksinim} className="madde-satiri">
                  <Cip renk={renk} metin={gereksinim} />
                  <span className="madde-satiri-ad">{metin}</span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </details>
  );
}

function dakika(iso: string): number {
  return Math.round((new Date(iso).getTime() - Date.now()) / 60000);
}

function saat(iso: string): string {
  return new Date(iso).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
}

function BugunListesi({ onAc }: { onAc: (runId: string) => void }) {
  const liste = useQuery({ queryKey: ['saha-bugun'], queryFn: () => gununCalistirmalari() });

  return (
    <div className="yigin">
      <header className="sayfa-basligi">
        <div>
          <h1>{tr.saha.baslik}</h1>
          <p className="sayfa-basligi-alt">{tr.saha.altBaslik}</p>
        </div>
      </header>

      {liste.isPending && <IskeletListe satirlar={3} />}
      {liste.isError && <Hata hata={liste.error} metin={tr.hata.aglaBaglanilamadi} />}
      {liste.data?.length === 0 && <p className="bos-durum">{tr.saha.listeYok}</p>}

      <ul className="liste-yigin">
        {liste.data?.map((run) => {
          const kalan = dakika(run.tolerance_end);
          const acilisa = dakika(run.writable_from);
          // "Açılabilir" = sunucunun cevap kabul edeceği aralık. Pencere
          // açılmadan önce liste görülebilir ama doldurulamaz, o yüzden
          // birincil düğme (davet) değil ikincil düğme (bak) gösterilir.
          const acilabilir =
            (run.status === 'scheduled' || run.status === 'in_progress') && acilisa <= 0;
          return (
            <li key={run.id} className="kart">
              <div className="yigin yigin--dar">
                <div className="kart-serit">
                  <strong className="kart-serit-ad">{run.branch_name}</strong>
                  <Cip
                    renk={run.status === 'submitted' ? 'marka' : acilabilir ? 'uyari' : 'pasif'}
                    metin={
                      tr.plan.durumlar[run.status as keyof typeof tr.plan.durumlar] ?? run.status
                    }
                  />
                </div>
                <p className="meta">
                  {tr.saha.pencere}: {saat(run.window_start)}–{saat(run.window_end)} ·{' '}
                  {acilisa > 0
                    ? `${tr.saha.acilis} ${saat(run.writable_from)}`
                    : tr.saha.kalan(kalan)}
                </p>
                <div className="eylemler">
                  {/* Kapanmış liste de açılıyor ama **okumak** için:
                      personel neyin sorulduğunu görebilmeli. Düğmenin
                      yazısı hangisi olduğunu söylüyor. */}
                  <Dugme
                    gorunum={acilabilir ? 'birincil' : 'ikincil'}
                    type="button"
                    onClick={() => onAc(run.id)}
                  >
                    {acilabilir ? tr.saha.ac : tr.saha.gor}
                  </Dugme>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ListeCalistirma({ runId, onKapat }: { runId: string; onKapat: () => void }) {
  const kuyruk = useQueryClient();
  const gorunum = useQuery({
    queryKey: ['saha-run', runId],
    queryFn: () => calistirmaGorunumu(runId),
  });

  // Seçenek etiketleri çalıştırma görünümünde yok, şablon sürümünde:
  // cihaz sürümü bir kez indirip saklıyor (senk manifesti tasarımı).
  const manifest = useQuery({ queryKey: ['saha-manifest'], queryFn: senkManifesti });
  const versionId = manifest.data?.runs.find((r) => r.run_id === runId)?.template_version_id;
  const surum = useQuery({
    queryKey: ['saha-surum', versionId],
    queryFn: () => surumDetayi(versionId as string),
    enabled: versionId != null,
  });

  const gonder = useMutation({
    mutationFn: () => listeyiGonder(runId),
    onSuccess: async () => {
      await kuyruk.invalidateQueries({ queryKey: ['saha-run', runId] });
      await kuyruk.invalidateQueries({ queryKey: ['saha-bugun'] });
    },
  });

  if (gorunum.isPending) return <Yukleniyor />;
  if (gorunum.isError || !gorunum.data) return <Hata hata={gorunum.error} />;

  const veri = gorunum.data;
  // Talimat satırı cevaplanmaz (sunucu da puanlamıyor), o yüzden ne paya
  // ne paydaya girer. Eskiden ikisine de giriyordu: hiç dokunulmamış
  // listede sayaç "1/8" yazıyordu.
  const maddeler = veri.sections.flatMap((b) => b.items).filter((m) => m.type !== 'instruction');
  const cevaplanan = maddeler.filter((m) => m.answer !== null).length;
  // Tolerans geçtiyse cevap yazılamaz: sunucu da reddeder, ekranın
  // denemeye davet etmesi anlamsız.
  const kacirildi = veri.status === 'missed';
  // Pencere (hazırlık payı dahil) daha açılmadıysa liste okunur ama
  // yazılamaz: sunucu `pencere-acilmadi` ile reddediyor, ekran da
  // doldurulamayacak bir listeyi doldurmaya davet etmemeli.
  const acilisaKalan = dakika(veri.writable_from);
  const acilmadi = acilisaKalan > 0;
  const kapali =
    veri.status === 'submitted' || veri.status === 'cancelled' || kacirildi || acilmadi;
  const gecikti = !kapali && new Date(veri.window_end).getTime() < Date.now();
  const problem = problemCoz(gonder.error);

  /** Seçenek etiketleri: sürüm detayından madde kimliğine göre. */
  function secenekler(itemId: string): { label: string; passing?: boolean }[] {
    for (const bolum of surum.data?.sections ?? []) {
      for (const madde of bolum.items) {
        if (madde.id === itemId) return madde.options ?? [];
      }
    }
    return [];
  }

  return (
    <div className="yigin">
      <header className="sayfa-basligi">
        <div>
          <h1>{veri.branch_name}</h1>
          <p className="sayfa-basligi-alt">
            {veri.template_name} · {saat(veri.window_start)}–{saat(veri.window_end)} ·{' '}
            {tr.saha.ilerleme(cevaplanan, maddeler.length)}
          </p>
        </div>
        <div className="sayfa-basligi-denetimler">
          <Dugme gorunum="sessiz" type="button" onClick={onKapat}>
            {tr.saha.geri}
          </Dugme>
        </div>
      </header>

      {acilmadi && <p className="bildiri bildiri--uyari">{tr.saha.acilmadi(acilisaKalan)}</p>}
      {kacirildi && <p className="bildiri bildiri--uyari">{tr.saha.kacirildi}</p>}
      {kapali && !kacirildi && !acilmadi && (
        <p className="bildiri bildiri--saglam">{tr.saha.kapandi}</p>
      )}
      {gecikti && <p className="bildiri bildiri--uyari">{tr.saha.pencereKapali}</p>}

      {veri.sections.map((bolum) => (
        <section key={bolum.id} className="yigin yigin--dar">
          <h2 className="bolum-etiketi">{bolum.title}</h2>
          <ul className="liste-yigin">
            {bolum.items.map((madde) => (
              <MaddeKarti
                key={madde.item_id}
                runId={runId}
                madde={madde}
                secenekler={secenekler(madde.item_id)}
                kilitli={kapali}
              />
            ))}
          </ul>
        </section>
      ))}

      {veri.blockers.length > 0 && !kapali && (
        <div role="status" className="bildiri bildiri--uyari">
          <strong>{tr.saha.gonderimEngeli}</strong>
          <ul className="madde-listesi">
            {veri.blockers.map((eksik) => (
              <li key={`${eksik.item_id}-${eksik.kind}`}>
                {eksik.title} — {tr.calistirma.eksikTuru[eksik.kind]}
              </li>
            ))}
          </ul>
        </div>
      )}

      {gonder.isSuccess && <p className="bildiri bildiri--saglam">{tr.saha.gonderildi}</p>}
      {problem && (
        <p role="alert" className="bildiri bildiri--hata">
          {problem.errors?.length ? problem.errors[0].sebep : problem.title}
        </p>
      )}

      {!kapali && (
        <div className="eylemler">
          <Dugme
            type="button"
            tam
            disabled={gonder.isPending || veri.blockers.length > 0}
            onClick={() => gonder.mutate()}
          >
            {tr.saha.gonder}
          </Dugme>
        </div>
      )}
    </div>
  );
}

function MaddeKarti({
  runId,
  madde,
  secenekler,
  kilitli,
}: {
  runId: string;
  madde: MaddeDurumu;
  secenekler: { label: string; passing?: boolean }[];
  kilitli: boolean;
}) {
  const kuyruk = useQueryClient();
  const [deger, setDeger] = useState<string>(
    madde.answer?.value != null ? String(madde.answer.value) : '',
  );
  const [sebepAcik, setSebepAcik] = useState(false);
  const [yukleniyor, setYukleniyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);

  // Cevap kimliği **cihazda** üretiliyor ve kalıcı: aynı maddeye ikinci
  // kez yazmak yeni kayıt açmıyor, mevcut cevabı güncelliyor (FR-0707).
  const [answerId] = useState(() => madde.answer?.id ?? crypto.randomUUID());

  const tazele = async () => {
    await kuyruk.invalidateQueries({ queryKey: ['saha-run', runId] });
  };

  const yaz = useMutation({
    mutationFn: (girdi: Parameters<typeof cevapYaz>[2]) => cevapYaz(runId, answerId, girdi),
    onSuccess: tazele,
    onError: (e) => setHata(problemCoz(e)?.title ?? tr.hata.genel),
  });

  async function fotografSec(dosya: File) {
    setHata(null);
    setYukleniyor(true);
    try {
      // Kanıt bir cevaba bağlanıyor: önce cevap yazılır, sonra dosya.
      if (madde.answer === null) {
        await cevapYaz(runId, answerId, { item_id: madde.item_id, state: 'passed' });
      }
      await kanitYukle(runId, answerId, madde.item_id, dosya);
      await tazele();
    } catch (e) {
      setHata(problemCoz(e)?.title ?? tr.hata.genel);
    } finally {
      setYukleniyor(false);
    }
  }

  const cevap = madde.answer;
  const aralikli = madde.min_value != null && madde.max_value != null;

  if (madde.type === 'instruction') {
    return (
      <li className="kart">
        <p className="ikincil-metin">{madde.title}</p>
      </li>
    );
  }

  return (
    <li className={cevap?.state === 'failed' ? 'kart kart--kritik' : 'kart'}>
      <div className="yigin yigin--dar">
        <div className="kart-serit">
          <strong className="kart-serit-ad">{madde.title}</strong>
          {madde.critical && <Cip renk="kritik" ikon="!" metin={tr.sablon.kritik} />}
          {madde.photo_required && <Cip renk="nötr" ikon="📷" metin={tr.sablon.fotografZorunlu} />}
          {cevap && (
            <Cip
              renk={
                cevap.state === 'passed' ? 'marka' : cevap.state === 'failed' ? 'kritik' : 'uyari'
              }
              ikon={cevap.state === 'passed' ? '✓' : cevap.state === 'failed' ? '✕' : '–'}
              metin={
                cevap.state === 'passed'
                  ? tr.calistirma.gecti
                  : cevap.state === 'failed'
                    ? tr.calistirma.gecmedi
                    : (cevap.not_done_reason_label ?? tr.calistirma.yapilamadi)
              }
            />
          )}
        </div>

        {!kilitli && (madde.type === 'confirm' || madde.type === 'photo') && (
          <div className="kart-serit">
            <Dugme
              gorunum="ikincil"
              boyut="kucuk"
              type="button"
              aria-pressed={cevap?.state === 'passed'}
              onClick={() => yaz.mutate({ item_id: madde.item_id, state: 'passed' })}
            >
              {tr.saha.yapildi}
            </Dugme>
            <Dugme
              gorunum="ikincil"
              boyut="kucuk"
              type="button"
              aria-pressed={cevap?.state === 'failed'}
              onClick={() => yaz.mutate({ item_id: madde.item_id, state: 'failed' })}
            >
              {tr.saha.yapilmadi}
            </Dugme>
          </div>
        )}

        {!kilitli && madde.type === 'choice' && secenekler.length > 0 && (
          <div className="cip-listesi">
            {secenekler.map((secenek) => (
              <Dugme
                key={secenek.label}
                gorunum="ikincil"
                boyut="kucuk"
                type="button"
                aria-pressed={cevap?.value === secenek.label}
                onClick={() =>
                  yaz.mutate({
                    item_id: madde.item_id,
                    state: secenek.passing === false ? 'failed' : 'passed',
                    value: secenek.label,
                  })
                }
              >
                {secenek.label}
              </Dugme>
            ))}
          </div>
        )}

        {!kilitli && (madde.type === 'number' || madde.type === 'temperature') && (
          <div className="alan-sirasi">
            <label className="alan-etiket">
              {tr.saha.olcum}
              {madde.unit ? ` (${madde.unit})` : ''}
              <input
                type="number"
                inputMode="decimal"
                step="0.1"
                className="alan alan--sayi"
                value={deger}
                onChange={(o) => setDeger(o.target.value)}
              />
            </label>
            <Dugme
              gorunum="ikincil"
              boyut="kucuk"
              type="button"
              disabled={deger === ''}
              onClick={() => {
                const sayi = Number(deger);
                const icinde =
                  !aralikli ||
                  (sayi >= (madde.min_value as number) && sayi <= (madde.max_value as number));
                yaz.mutate({
                  item_id: madde.item_id,
                  state: icinde ? 'passed' : 'failed',
                  value: sayi,
                });
              }}
            >
              {tr.saha.kaydedildi}
            </Dugme>
          </div>
        )}

        {!kilitli && madde.type === 'text' && (
          <div className="alan-sirasi">
            <label className="alan-etiket alan-etiket--genis">
              {tr.saha.notAlani}
              <input className="alan" value={deger} onChange={(o) => setDeger(o.target.value)} />
            </label>
            <Dugme
              gorunum="ikincil"
              boyut="kucuk"
              type="button"
              disabled={deger.trim() === ''}
              onClick={() =>
                yaz.mutate({ item_id: madde.item_id, state: 'passed', value: deger.trim() })
              }
            >
              {tr.saha.kaydedildi}
            </Dugme>
          </div>
        )}

        {aralikli && (
          <p className="alan-ipucu">
            {tr.saha.aralikDisi(
              madde.min_value as number,
              madde.max_value as number,
              madde.unit ?? '',
            )}
          </p>
        )}

        {!kilitli && (madde.photo_required || madde.type === 'photo') && (
          <div className="kart-serit">
            <label className="dugme dugme--ikincil dugme--kucuk">
              {yukleniyor ? tr.saha.fotografYukleniyor : tr.saha.fotografSec}
              <input
                type="file"
                accept="image/*"
                capture="environment"
                className="sr-only"
                disabled={yukleniyor}
                onChange={(o) => {
                  const dosya = o.target.files?.[0];
                  if (dosya) void fotografSec(dosya);
                  o.target.value = '';
                }}
              />
            </label>
            {cevap != null && cevap.evidence_count > 0 && (
              <span className="meta">{tr.saha.fotografSayisi(cevap.evidence_count)}</span>
            )}
          </div>
        )}

        {/* FR-0804: kritik madde atlanamaz, düğme hiç görünmez. */}
        {!kilitli && madde.critical && <p className="alan-ipucu">{tr.saha.kritikAtlanamaz}</p>}

        {!kilitli && !madde.critical && (
          <div className="kart-serit">
            {sebepAcik ? (
              <select
                className="alan"
                defaultValue=""
                onChange={(o) => {
                  if (o.target.value === '') return;
                  yaz.mutate({
                    item_id: madde.item_id,
                    state: 'not_done',
                    not_done_reason: o.target.value as Parameters<
                      typeof cevapYaz
                    >[2]['not_done_reason'],
                  });
                  setSebepAcik(false);
                }}
              >
                <option value="">{tr.saha.sebepSec}</option>
                {Object.entries(tr.saha.sebepler).map(([kod, etiket]) => (
                  <option key={kod} value={kod}>
                    {etiket}
                  </option>
                ))}
              </select>
            ) : (
              <Dugme
                gorunum="sessiz"
                boyut="kucuk"
                type="button"
                onClick={() => setSebepAcik(true)}
              >
                {tr.saha.yapilamadi}
              </Dugme>
            )}
          </div>
        )}

        {hata && (
          <p role="alert" className="hata-metni">
            {hata}
          </p>
        )}
      </div>
    </li>
  );
}
