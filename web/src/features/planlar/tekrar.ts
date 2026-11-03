import { tr } from '../../i18n/tr';

/**
 * Tekrar dizgesinin okunur hâli.
 *
 * Sunucu planı RFC 5545 kuralı olarak tutuyor (FR-0503) ve plan
 * listesinde bu dizge olduğu gibi ekrana yazılıyordu: şube müdürü
 * "FREQ=WEEKLY;BYDAY=MO,WE" okuyordu. Dizgeyi üreten de biziz
 * (`Zamanlama.rrule`), bu yüzden sözcük dağarcığı küçük ve kapalı.
 *
 * Tanımadığı dizgeyi **olduğu gibi** döndürüyor: yanlış bir cümle
 * uydurmak, çiğ kuralı göstermekten kötüdür.
 */
export function tekrarMetni(kural: string): string {
  const satirlar = kural
    .split('\n')
    .map((x) => x.replace(/^RRULE:/, '').trim())
    .filter(Boolean);
  if (satirlar.length === 0) return kural;

  const parcalar = alanlar(satirlar[0]);
  const govde = tekrarGovdesi(parcalar);
  if (govde === null) return kural;

  const ekler = [saatler(satirlar), bitis(parcalar)].filter(Boolean);
  return ekler.length > 0 ? `${govde} · ${ekler.join(' · ')}` : govde;
}

function alanlar(satir: string): Map<string, string> {
  return new Map(
    satir
      .split(';')
      .map((x) => x.split('='))
      .filter((x) => x.length === 2)
      .map(([ad, deger]) => [ad.toUpperCase(), deger]),
  );
}

function tekrarGovdesi(p: Map<string, string>): string | null {
  const siklik = p.get('FREQ');
  if (siklik === 'DAILY') return p.get('COUNT') === '1' ? tr.plan.tekSeferlik : tr.plan.herGun;

  if (siklik === 'WEEKLY') {
    const gunler = (p.get('BYDAY') ?? '')
      .split(',')
      .map((kod) => gunAdi(kod))
      .filter((ad): ad is string => ad !== null);
    return gunler.length > 0 ? `Her ${gunler.join(', ')}` : null;
  }

  if (siklik === 'MONTHLY') {
    const ayinGunu = p.get('BYMONTHDAY');
    if (ayinGunu) return tr.plan.ayinGununde(Number(ayinGunu));

    // "2TU", "-1FR": kaçıncı hafta + gün kodu.
    const eslesme = /^(-?\d+)([A-Z]{2})$/.exec(p.get('BYDAY') ?? '');
    if (!eslesme) return null;
    const sira = ninciAdi(Number(eslesme[1]));
    const gun = gunAdi(eslesme[2]);
    return sira && gun ? tr.plan.ayinNincisi(sira, gun) : null;
  }

  return null;
}

const GUN_KODLARI = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU'];

function gunAdi(kod: string): string | null {
  const sira = GUN_KODLARI.indexOf(kod.trim().toUpperCase());
  return sira === -1 ? null : tr.plan.gunAdlari[sira];
}

function ninciAdi(sira: number): string | null {
  if (sira === -1) return tr.plan.ninci[4];
  return sira >= 1 && sira <= 4 ? tr.plan.ninci[sira - 1] : null;
}

/** Gün içinde birden çok pencere: her saat ayrı bir `RRULE` satırı. */
function saatler(satirlar: string[]): string {
  if (satirlar.length < 2) return '';
  const liste = satirlar.map((satir) => {
    const p = alanlar(satir);
    const sa = p.get('BYHOUR');
    const dk = p.get('BYMINUTE') ?? '0';
    return sa === undefined ? null : `${iki(sa)}:${iki(dk)}`;
  });
  return liste.every((x) => x !== null) ? liste.join(', ') : '';
}

function bitis(p: Map<string, string>): string {
  const deger = p.get('UNTIL');
  const eslesme = /^(\d{4})(\d{2})(\d{2})/.exec(deger ?? '');
  if (!eslesme) return '';
  const [, yil, ay, gun] = eslesme;
  return tr.plan.kadar(`${gun}.${ay}.${yil}`);
}

function iki(sayi: string): string {
  return sayi.padStart(2, '0');
}
