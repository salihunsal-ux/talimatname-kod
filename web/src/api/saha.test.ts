import { describe, expect, it } from 'vitest';

import { DesteklenmeyenTur, kanitTuru } from './saha';

function dosya(tur: string, ad = 'foto'): File {
  return new File([new Uint8Array([1, 2, 3])], ad, { type: tur });
}

describe('kanıt dosya türü (bağımsız test turu B12)', () => {
  it('JPEG ve PNG olduğu gibi gider', () => {
    expect(kanitTuru(dosya('image/jpeg'))).toBe('image/jpeg');
    expect(kanitTuru(dosya('image/png'))).toBe('image/png');
    expect(kanitTuru(dosya('IMAGE/JPEG'))).toBe('image/jpeg');
    expect(kanitTuru(dosya('image/jpg'))).toBe('image/jpeg');
  });

  it('WebP/HEIC/GIF artık JPEG diye etiketlenmiyor, reddediliyor', () => {
    // Eski sürüm PNG dışındaki her dosyaya `image/jpeg` yazıp baytları
    // dönüştürmüyordu: depodaki kayıt yalan söylüyor, önizleme
    // bozulabiliyordu. Dönüştürmek de doğru değil — kanıtın baytları
    // değişirse damgalanan şey çekilen dosya olmaz.
    for (const tur of ['image/webp', 'image/heic', 'image/gif', 'application/pdf', '']) {
      expect(() => kanitTuru(dosya(tur))).toThrow(DesteklenmeyenTur);
    }
  });

  it('hata türü ekranda yazılabilsin diye taşınıyor', () => {
    try {
      kanitTuru(dosya('image/heic'));
      expect.unreachable('reddetmeliydi');
    } catch (e) {
      expect(e).toBeInstanceOf(DesteklenmeyenTur);
      expect((e as DesteklenmeyenTur).tur).toBe('image/heic');
    }
  });
});
