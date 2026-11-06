import { problemCoz } from '../api/client';
import { cikisYap } from '../api/oturum';
import { tr } from '../i18n/tr';
import { Dugme } from './Dugme';

/**
 * Yükleniyor ve hata satırları on bir ekranda aynı iki satırı elde
 * yazıyordu. Hata artık kırmızı bir cümle değil `.bildiri--hata`
 * kutusu: ekranın geri kalanı yerinde dururken hatanın sınırı olsun.
 */
export function Yukleniyor({ metin }: { metin?: string }) {
  return <p className="durum-metni">{metin ?? tr.genel.yukleniyor}</p>;
}

/** Sunucunun oturum reddi; davranış `type`a bakar, başlık metni değil. */
const OTURUM_GECERSIZ = 'urn:talimatname:belirtec-gecersiz';

/**
 * Hata kutusu.
 *
 * Metni **sunucunun kendi cümlesinden** alıyor: yanıtta problem
 * gövdesi varsa sunucu ulaşılmış demektir ve ne dediği yazılır.
 * `metin` yalnızca gövde çözülemediğinde (gerçek ağ hatası)
 * kullanılan yedek. Önce her ekran sabit "Sunucuya bağlanılamadı"
 * yazıyordu: oturum süresi dolduğunda da bu çıkıyordu, oysa sunucu
 * gayet iyi cevap vermişti — kullanıcı ağını kontrol etmeye gidiyordu.
 */
export function Hata({ hata, metin }: { hata?: unknown; metin?: string }) {
  const problem = problemCoz(hata);
  const sebep = problem?.errors?.length ? `: ${problem.errors[0].sebep}` : '';
  const yazi = problem ? `${problem.title}${sebep}` : (metin ?? tr.hata.aglaBaglanilamadi);

  // Oturum düştüyse sayfayı yenilemek kurtarmaz; belirteci bırakıp
  // giriş ekranına dönmek gerekiyor.
  if (problem?.type === OTURUM_GECERSIZ) {
    return (
      <div role="alert" className="bildiri bildiri--hata yigin yigin--dar">
        <span>{yazi}</span>
        <div className="eylemler">
          <Dugme
            gorunum="ikincil"
            boyut="kucuk"
            type="button"
            onClick={() => {
              cikisYap();
              window.location.reload();
            }}
          >
            {tr.hata.yenidenGir}
          </Dugme>
        </div>
      </div>
    );
  }

  return (
    <p role="alert" className="bildiri bildiri--hata">
      {yazi}
    </p>
  );
}
