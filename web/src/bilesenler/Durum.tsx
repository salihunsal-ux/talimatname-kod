import { tr } from '../i18n/tr';

/**
 * Yükleniyor ve hata satırları on bir ekranda aynı iki satırı elde
 * yazıyordu. Hata artık kırmızı bir cümle değil `.bildiri--hata`
 * kutusu: ekranın geri kalanı yerinde dururken hatanın sınırı olsun.
 */
export function Yukleniyor({ metin }: { metin?: string }) {
  return <p className="durum-metni">{metin ?? tr.genel.yukleniyor}</p>;
}

export function Hata({ metin }: { metin?: string }) {
  return (
    <p role="alert" className="bildiri bildiri--hata">
      {metin ?? tr.hata.genel}
    </p>
  );
}
