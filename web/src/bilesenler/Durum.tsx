import { problemCoz } from '../api/client';
import { tr } from '../i18n/tr';

/**
 * Yükleniyor ve hata satırları on bir ekranda aynı iki satırı elde
 * yazıyordu. Hata artık kırmızı bir cümle değil `.bildiri--hata`
 * kutusu: ekranın geri kalanı yerinde dururken hatanın sınırı olsun.
 */
export function Yukleniyor({ metin }: { metin?: string }) {
  return <p className="durum-metni">{metin ?? tr.genel.yukleniyor}</p>;
}

export function Hata({ hata, metin }: { hata?: unknown; metin?: string }) {
  const problem = problemCoz(hata);
  const sebep = problem?.errors?.length ? `: ${problem.errors[0].sebep}` : '';
  const yazi = problem ? `${problem.title}${sebep}` : (metin ?? tr.hata.aglaBaglanilamadi);

  return (
    <p role="alert" className="bildiri bildiri--hata">
      {yazi}
    </p>
  );
}
