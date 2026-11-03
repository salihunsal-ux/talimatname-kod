import { describe, expect, it } from 'vitest';

import { tekrarMetni } from './tekrar';

describe('tekrarMetni', () => {
  it('günlük ve tek seferlik kuralı ayırır', () => {
    expect(tekrarMetni('FREQ=DAILY')).toBe('Her gün');
    expect(tekrarMetni('FREQ=DAILY;COUNT=1')).toBe('Tek seferlik');
  });

  it('haftalık kuralda gün adlarını yazar', () => {
    expect(tekrarMetni('FREQ=WEEKLY;BYDAY=MO,WE')).toBe('Her Pazartesi, Çarşamba');
  });

  it('ayın gününü ve ayın n’inci gününü yazar', () => {
    expect(tekrarMetni('FREQ=MONTHLY;BYMONTHDAY=15')).toBe('Ayın 15. günü');
    expect(tekrarMetni('FREQ=MONTHLY;BYDAY=2TU')).toBe('Ayın ikinci Salı günü');
    expect(tekrarMetni('FREQ=MONTHLY;BYDAY=-1FR')).toBe('Ayın son Cuma günü');
  });

  it('bitiş tarihini ekler', () => {
    expect(tekrarMetni('FREQ=DAILY;UNTIL=20261231T235959')).toBe(
      'Her gün · 31.12.2026 sonuna kadar',
    );
  });

  it('gün içi pencerelerin saatlerini toplar', () => {
    // Sunucu her pencere için ayrı bir RRULE satırı yazıyor
    // (Zamanlama.rrule): "BYHOUR=9,14" dört pencere üretirdi.
    const kural = 'RRULE:FREQ=DAILY;BYHOUR=9;BYMINUTE=0\nRRULE:FREQ=DAILY;BYHOUR=14;BYMINUTE=30';
    expect(tekrarMetni(kural)).toBe('Her gün · 09:00, 14:30');
  });

  it('tanımadığı kuralı olduğu gibi döndürür', () => {
    // Uydurulmuş bir cümle, çiğ kuraldan kötü: plan yanlış okunur.
    expect(tekrarMetni('FREQ=YEARLY;BYMONTH=3')).toBe('FREQ=YEARLY;BYMONTH=3');
    expect(tekrarMetni('FREQ=WEEKLY')).toBe('FREQ=WEEKLY');
    expect(tekrarMetni('')).toBe('');
  });
});
