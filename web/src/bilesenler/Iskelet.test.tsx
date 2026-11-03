import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { IskeletKutular, IskeletTablo } from './Iskelet';

afterEach(() => {
  vi.useRealTimers();
});

describe('İskelet', () => {
  it('kısa beklemede hiçbir şey göstermiyor', () => {
    // 250 ms'nin altında yanıtlanan istek için gri kutuların bir an
    // parlayıp kaybolması, hiç göstermemekten kötü.
    vi.useFakeTimers();
    render(<IskeletTablo sutunlar={4} />);

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('bekleme uzayınca görünüyor ve "yükleniyor" diyor', () => {
    vi.useFakeTimers();
    render(<IskeletTablo sutunlar={4} />);

    act(() => vi.advanceTimersByTime(300));

    const alan = screen.getByRole('status');
    expect(alan).toHaveAttribute('aria-busy', 'true');
    // Ekran okuyucu için değişen bir şey yok: aynı cümle duyuluyor.
    expect(alan).toHaveTextContent('Yükleniyor…');
  });

  it('tablo iskeleti gerçek sütun sayısını kuruyor', () => {
    // Sütun sayısı tutmazsa veri gelince satırlar yeniden dizilir ve
    // sayfa zıplar — iskeletin önlediği şey tam olarak bu.
    vi.useFakeTimers();
    const { container } = render(<IskeletTablo sutunlar={5} satirlar={3} />);

    act(() => vi.advanceTimersByTime(300));

    const satirlar = container.querySelectorAll('tbody tr');
    expect(satirlar).toHaveLength(3);
    expect(satirlar[0].querySelectorAll('td')).toHaveLength(5);
  });

  it('gri kutular ekran okuyucudan gizli', () => {
    vi.useFakeTimers();
    const { container } = render(<IskeletKutular adet={3} />);

    act(() => vi.advanceTimersByTime(300));

    const kutular = container.querySelectorAll('.iskelet');
    expect(kutular).toHaveLength(3);
    for (const kutu of kutular) expect(kutu).toHaveAttribute('aria-hidden', 'true');
  });
});
