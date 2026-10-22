import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  sablonListesi,
  surumDetayi,
  surumYayinla,
  taslakKaydet,
  type SurumDetay,
} from '../../api/sablonlar';
import { SablonlarSayfasi } from './SablonlarSayfasi';

vi.mock('../../api/sablonlar');
const liste = vi.mocked(sablonListesi);
const detay = vi.mocked(surumDetayi);
const kaydet = vi.mocked(taslakKaydet);
const yayinla = vi.mocked(surumYayinla);

const TASLAK: SurumDetay = {
  id: 'v-1',
  template_id: 't-1',
  template_name: 'Açılış',
  version_no: 1,
  status: 'draft',
  published_at: null,
  scored_item_count: 1,
  critical_item_count: 0,
  photo_item_count: 0,
  camera_only: true,
  sections: [
    {
      id: 's-1',
      order: 1,
      title: 'Hazırlık',
      items: [
        {
          id: 'm-1',
          type: 'confirm',
          type_label: 'Onay',
          title: 'Espresso makinesi açıldı',
          hint: null,
          required: true,
          photo_required: false,
          critical: false,
          options: [],
          min_value: null,
          max_value: null,
          unit: null,
          scored: true,
        },
      ],
    },
  ],
  publish_issues: [],
};

function kur() {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={istemci}>
      <SablonlarSayfasi />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  liste.mockResolvedValue([
    {
      id: 't-1',
      name: 'Açılış',
      category: null,
      versions: [
        {
          id: 'v-1',
          version_no: 1,
          status: 'draft',
          published_at: null,
          scored_item_count: 1,
          critical_item_count: 0,
          photo_item_count: 0,
        },
      ],
    },
  ]);
  detay.mockResolvedValue(TASLAK);
});

describe('Şablonlar sayfası', () => {
  it('taslak sürüm düzenlenebilir', async () => {
    kur();
    expect(await screen.findByText('Espresso makinesi açıldı')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Madde ekle' })).toBeInTheDocument();
  });

  it('madde eklenince kaydedilmemiş değişiklik uyarısı çıkar ve yayın kilitlenir', async () => {
    kur();
    await screen.findByText('Espresso makinesi açıldı');

    await userEvent.type(screen.getByLabelText('Madde başlığı'), 'Süt dolabı sıcaklığı');
    await userEvent.selectOptions(screen.getByLabelText('Madde türü'), 'temperature');
    await userEvent.click(screen.getByRole('button', { name: 'Madde ekle' }));

    expect(screen.getByText('Kaydedilmemiş değişiklik var')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Yayınla' })).toBeDisabled();
    expect(screen.getByText('0–4 °C')).toBeInTheDocument(); // sıcaklıkta varsayılan aralık
  });

  it('taslak kaydedilince sunucuya bölümler gönderilir', async () => {
    kaydet.mockResolvedValue(TASLAK);
    kur();
    await screen.findByText('Espresso makinesi açıldı');

    await userEvent.type(screen.getByLabelText('Madde başlığı'), 'Yeni madde');
    await userEvent.click(screen.getByRole('button', { name: 'Madde ekle' }));
    await userEvent.click(screen.getByRole('button', { name: 'Taslağı kaydet' }));

    expect(kaydet).toHaveBeenCalledWith('v-1', {
      camera_only: true,
      sections: expect.arrayContaining([
        expect.objectContaining({
          title: 'Hazırlık',
          items: expect.arrayContaining([expect.objectContaining({ title: 'Yeni madde' })]),
        }),
      ]),
    });
  });

  it('yayın engelleri listelenir ve yayın düğmesi kapanır', async () => {
    detay.mockResolvedValue({
      ...TASLAK,
      publish_issues: [
        { where: 'm-1', message: 'Çoktan seçmeli maddede en az iki seçenek olmalı' },
        { where: 'm-2', message: 'Alt ve üst sınır girilmeli' },
      ],
    });

    kur();
    expect(await screen.findByText('Yayına engel olanlar:')).toBeInTheDocument();
    expect(screen.getByText('Alt ve üst sınır girilmeli')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Yayınla' })).toBeDisabled();
    expect(yayinla).not.toHaveBeenCalled();
  });

  it('yayınlanmış sürüm düzenlenemez, yeni taslak önerilir', async () => {
    detay.mockResolvedValue({
      ...TASLAK,
      status: 'published',
      published_at: '2026-11-02T06:00:00Z',
    });

    kur();
    await screen.findByText('Espresso makinesi açıldı');

    expect(screen.queryByRole('button', { name: 'Madde ekle' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Yeni taslak türet' })).toBeInTheDocument();
  });
});
