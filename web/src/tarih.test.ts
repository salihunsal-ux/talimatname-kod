import { afterEach, describe, expect, it, vi } from 'vitest';

import { bugunIso, gunIso, sonGunler } from './tarih';

afterEach(() => {
  vi.useRealTimers();
});

describe('tarih (bağımsız test turu B11)', () => {
  it('gece yarısından sonra gün bir geriye düşmüyor', () => {
    // İstanbul'da 8 Kasım 00:30 → UTC'de 7 Kasım 21:30. Eski kesim
    // (toISOString) burada "2026-11-07" veriyordu: pano dünü açıyor,
    // plan dünden başlıyordu.
    const geceYarisindanSonra = new Date(2026, 10, 8, 0, 30);

    expect(gunIso(geceYarisindanSonra)).toBe('2026-11-08');
    expect(geceYarisindanSonra.toISOString().slice(0, 10)).not.toBe('2026-11-08');
  });

  it('gün batımından önce de aynı günü veriyor', () => {
    expect(gunIso(new Date(2026, 10, 7, 23, 59))).toBe('2026-11-07');
    expect(gunIso(new Date(2026, 10, 7, 3, 0))).toBe('2026-11-07');
  });

  it('ay ve gün iki hane', () => {
    expect(gunIso(new Date(2026, 0, 5, 12, 0))).toBe('2026-01-05');
  });

  it('bugün yerel günü veriyor', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 10, 8, 2, 59));

    expect(bugunIso()).toBe('2026-11-08');
  });

  it('aralık iki ucu da yerel gün', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 10, 8, 1, 0));

    expect(sonGunler(7)).toEqual({ ilk: '2026-11-01', son: '2026-11-08' });
  });
});
