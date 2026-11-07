import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Oturumlu } from '../test/oturum';
import { BOLGE_MUDURU, SUBE_MUDURU, YONETICI } from '../test/kullanicilar';
import type { Ben } from '../api/oturum';
import { Kabuk } from './Kabuk';

/**
 * Menü kapısı sunucudaki kapıyla birebir olmalı.
 *
 * Bağımsız test turu O-1: tek bir `yonetim` bayrağı kullanılıyordu ve
 * bölge müdürü Bildirimler ile Kurulum'u menüde görüp tıklayınca 403
 * alıyordu. Gösterilen her madde açılabilmeli.
 */
function menu(ben: Ben): string[] {
  render(
    <Oturumlu ben={ben}>
      <Kabuk bolum="pano" onBolum={() => undefined}>
        <p>içerik</p>
      </Kabuk>
    </Oturumlu>,
  );
  return screen
    .getAllByRole('button')
    .map((d) => d.textContent?.trim() ?? '')
    .filter(Boolean);
}

describe('Kabuk menüsü', () => {
  it('yöneticiye bütün bölümleri gösteriyor', () => {
    const maddeler = menu(YONETICI);

    expect(maddeler).toEqual(
      expect.arrayContaining(['Pano', 'Personel', 'Bildirimler', 'Kurulum']),
    );
  });

  it('bölge müdürüne yalnızca yöneticiye açık bölümleri göstermiyor', () => {
    // Sunucu: /notifications ve /setup* yalnızca `Yonetici`.
    const maddeler = menu(BOLGE_MUDURU);

    expect(maddeler).not.toContain('Bildirimler');
    expect(maddeler).not.toContain('Kurulum');
    // Personel sunucuda `Mudur` kapısında: bölge müdürü girebiliyor.
    expect(maddeler).toContain('Personel');
  });

  it('şube müdürüne yönetim bölümlerini göstermiyor', () => {
    const maddeler = menu(SUBE_MUDURU);

    expect(maddeler).not.toContain('Personel');
    expect(maddeler).not.toContain('Bildirimler');
    expect(maddeler).not.toContain('Kurulum');
    expect(maddeler).toContain('Raporlar');
  });
});
