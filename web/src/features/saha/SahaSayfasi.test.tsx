import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { calistirmaGorunumu, type CalistirmaGorunumu } from '../../api/calistirma';
import { gununCalistirmalari } from '../../api/planlar';
import { senkManifesti, surumDetayi } from '../../api/saha';
import type { Ben } from '../../api/oturum';
import { Oturumlu } from '../../test/oturum';
import { PERSONEL, SUBE_MUDURU } from '../../test/kullanicilar';
import { SahaSayfasi } from './SahaSayfasi';

vi.mock('../../api/calistirma');
vi.mock('../../api/planlar');
vi.mock('../../api/saha');

const gorunum = vi.mocked(calistirmaGorunumu);
const bugun = vi.mocked(gununCalistirmalari);
const manifest = vi.mocked(senkManifesti);
const surum = vi.mocked(surumDetayi);

function madde(ek: Record<string, unknown>) {
  return {
    item_id: 'm-1',
    title: 'Madde',
    type: 'confirm',
    type_label: 'Onay',
    required: true,
    photo_required: false,
    critical: false,
    min_value: null,
    max_value: null,
    unit: null,
    answer: null,
    ...ek,
  };
}

const CALISTIRMA = {
  run_id: 'r-1',
  branch_id: 'b-1',
  branch_name: 'Kadıköy',
  region_name: 'Anadolu',
  business_day: '2026-11-05',
  status: 'scheduled',
  result: null,
  score_percent: null,
  window_start: '2026-11-05T19:00:00Z',
  writable_from: '2026-11-05T18:45:00Z',
  window_end: '2026-11-05T22:30:00Z',
  tolerance_end: '2026-11-05T23:30:00Z',
  submitted_at: null,
  template_name: 'Kapanış (kafe)',
  locked_by: null,
  blockers: [],
  sections: [
    {
      id: 's-1',
      title: 'Güvenlik',
      items: [
        madde({ item_id: 'm-1', title: 'Gaz vanası kapatıldı', critical: true }),
        madde({ item_id: 'm-2', title: 'Tezgâh silindi', critical: false }),
      ],
    },
  ],
} as unknown as CalistirmaGorunumu;

function kur(ben: Ben | null = null) {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={istemci}>
      <Oturumlu ben={ben}>
        <SahaSayfasi />
      </Oturumlu>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  bugun.mockResolvedValue([
    {
      id: 'r-1',
      plan_name: 'Günlük kapanış',
      branch_name: 'Kadıköy',
      status: 'scheduled',
      window_start: '2026-11-05T19:00:00Z',
      writable_from: '2026-11-05T18:45:00Z',
      window_end: '2026-11-05T22:30:00Z',
      tolerance_end: '2026-11-05T23:30:00Z',
    },
  ] as never);
  gorunum.mockResolvedValue(CALISTIRMA);
  manifest.mockResolvedValue({ runs: [], template_versions: [] } as never);
  surum.mockResolvedValue({ sections: [] } as never);
});

describe('Saha istemcisi', () => {
  it('kritik maddede “Yapılamadı” düğmesi yok (FR-0804)', async () => {
    kur();
    await userEvent.click(await screen.findByRole('button', { name: 'Listeyi aç' }));

    // Madde atlanamaz: düğme gizlenmiyor, hiç çizilmiyor. Listede iki
    // madde var ve yalnızca kritik olmayanda düğme bulunmalı.
    expect(await screen.findByText('Gaz vanası kapatıldı')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Yapılamadı' })).toHaveLength(1);
    expect(screen.getByText(/Kritik madde atlanamaz/)).toBeInTheDocument();
  });

  it('neyin eksik olduğunu ekranda sayıyor', async () => {
    // Eksikler belgede değil ekranda: bu istemciyi gören herkes
    // neyin olmadığını da görsün.
    kur();

    const katlanir = await screen.findByText(/Bu istemcide olmayanlar/);
    // 13 idi; FR-0521 (çalıştırma kilidi ekranda) yazılınca 12'ye düştü.
    expect(katlanir).toHaveTextContent('(12)');

    await userEvent.click(katlanir);
    expect(screen.getByText(/Tarayıcı yapamıyor/)).toBeInTheDocument();
    expect(screen.getByText('FR-0604')).toBeInTheDocument();
  });

  it('demo olduğunu ve fotoğrafın galeri bayraklı yazıldığını söylüyor', async () => {
    kur();

    expect(await screen.findByText(/Pilot istemcisi değildir/)).toBeInTheDocument();
    expect(screen.getByText(/galeri bayrağıyla kaydedilir/)).toBeInTheDocument();
  });
});

describe('pencere kapısı ve ilerleme (bağımsız test turu Y-1, O-3)', () => {
  /** Listeyi, penceresi verilen anda açılacak biçimde kurar. */
  function pencere(acilis: Date, bitis: Date) {
    bugun.mockResolvedValue([
      {
        id: 'r-1',
        plan_name: 'Günlük kapanış',
        branch_name: 'Kadıköy',
        status: 'scheduled',
        window_start: acilis.toISOString(),
        writable_from: acilis.toISOString(),
        window_end: bitis.toISOString(),
        tolerance_end: new Date(bitis.getTime() + 3_600_000).toISOString(),
      },
    ] as never);
    gorunum.mockResolvedValue({
      ...CALISTIRMA,
      window_start: acilis.toISOString(),
      writable_from: acilis.toISOString(),
      window_end: bitis.toISOString(),
      tolerance_end: new Date(bitis.getTime() + 3_600_000).toISOString(),
    } as unknown as CalistirmaGorunumu);
  }

  it('penceresi açılmamış listeyi doldurmaya davet etmiyor', async () => {
    // Kapanış listesi gece açılacak; öğlen "Listeyi aç" demek
    // doldurulamayacak bir işe çağırmaktı (sunucu `pencere-acilmadi`).
    const sonra = new Date(Date.now() + 6 * 3_600_000);
    pencere(sonra, new Date(sonra.getTime() + 3_600_000));
    kur();

    expect(await screen.findByRole('button', { name: 'Listeyi gör' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Listeyi aç' })).not.toBeInTheDocument();
  });

  it('açılmamış liste okunur ama cevap düğmeleri kilitli', async () => {
    const sonra = new Date(Date.now() + 6 * 3_600_000);
    pencere(sonra, new Date(sonra.getTime() + 3_600_000));
    kur();
    await userEvent.click(await screen.findByRole('button', { name: 'Listeyi gör' }));

    expect(await screen.findByText(/Pencere henüz açılmadı/)).toBeInTheDocument();
    expect(screen.getByText('Tezgâh silindi')).toBeInTheDocument();
  });

  it('penceresi açık listeyi doldurmaya çağırıyor', async () => {
    const once = new Date(Date.now() - 10 * 60_000);
    pencere(once, new Date(Date.now() + 3_600_000));
    kur();

    expect(await screen.findByRole('button', { name: 'Listeyi aç' })).toBeInTheDocument();
  });

  it('ilerleme sayacı talimat satırını saymıyor', async () => {
    // Dokunulmamış listede "1/8" yazıyordu: talimat satırı hem paya hem
    // paydaya giriyordu. Doğrusu "0/2" (iki cevaplanır madde).
    const once = new Date(Date.now() - 10 * 60_000);
    pencere(once, new Date(Date.now() + 3_600_000));
    gorunum.mockResolvedValue({
      ...CALISTIRMA,
      window_start: once.toISOString(),
      writable_from: once.toISOString(),
      window_end: new Date(Date.now() + 3_600_000).toISOString(),
      tolerance_end: new Date(Date.now() + 7_200_000).toISOString(),
      sections: [
        {
          id: 's-1',
          title: 'Güvenlik',
          items: [
            madde({ item_id: 'm-0', title: 'Sıra: mutfak → salon', type: 'instruction' }),
            madde({ item_id: 'm-1', title: 'Gaz vanası kapatıldı', critical: true }),
            madde({ item_id: 'm-2', title: 'Tezgâh silindi' }),
          ],
        },
      ],
    } as unknown as CalistirmaGorunumu);
    kur();
    await userEvent.click(await screen.findByRole('button', { name: 'Listeyi aç' }));

    expect(await screen.findByText(/0\/2 madde/)).toBeInTheDocument();
    expect(screen.queryByText(/1\/3 madde/)).not.toBeInTheDocument();
  });
});

describe('başarısız cevabın kanıtı (bağımsız test turu B01, B09)', () => {
  const ACILIS = new Date(Date.now() - 10 * 60_000).toISOString();
  const BITIS = new Date(Date.now() + 3_600_000).toISOString();

  /** Penceresi açık listeyi kurar ve detayını açar. */
  async function ac() {
    bugun.mockResolvedValue([
      {
        id: 'r-1',
        plan_name: 'Günlük kapanış',
        branch_name: 'Kadıköy',
        status: 'in_progress',
        window_start: ACILIS,
        writable_from: ACILIS,
        window_end: BITIS,
        tolerance_end: BITIS,
      },
    ] as never);
    kur();
    await userEvent.click(await screen.findByRole('button', { name: 'Listeyi aç' }));
  }

  /** Penceresi açık, sıcaklık maddesi başarısız cevaplanmış bir liste. */
  function basarisizListe(cevapEk: Record<string, unknown> = {}) {
    gorunum.mockResolvedValue({
      ...CALISTIRMA,
      status: 'in_progress',
      writable_from: ACILIS,
      window_start: ACILIS,
      window_end: BITIS,
      tolerance_end: BITIS,
      blockers: [
        { item_id: 'm-3', title: 'Süt dolabı sıcaklığı', kind: 'evidence' },
        { item_id: 'm-3', title: 'Süt dolabı sıcaklığı', kind: 'note' },
      ],
      sections: [
        {
          id: 's-1',
          title: 'Soğuk zincir',
          items: [
            madde({
              item_id: 'm-3',
              title: 'Süt dolabı sıcaklığı',
              type: 'temperature',
              type_label: 'Sıcaklık',
              min_value: 0,
              max_value: 4,
              unit: '°C',
              answer: {
                id: 'c-3',
                item_id: 'm-3',
                state: 'failed',
                value: 6,
                note: null,
                evidence_count: 0,
                answered_at: '2026-11-05T19:10:00Z',
                not_done_reason: null,
                not_done_reason_label: null,
                ...cevapEk,
              },
            }),
          ],
        },
      ],
    } as unknown as CalistirmaGorunumu);
  }

  it('başarısız cevapta açıklama alanı açılıyor (BR-06)', async () => {
    basarisizListe();
    await ac();

    expect(await screen.findByLabelText('Açıklama')).toBeTruthy();
  });

  it('başarısız cevapta fotoğraf düğmesi açılıyor — madde fotoğraf istemese de', async () => {
    basarisizListe();
    await ac();

    expect(await screen.findByText('Fotoğraf seç')).toBeTruthy();
  });

  it('geçen cevapta açıklama alanı yok: zorunlu olmayan alan sormuyoruz', async () => {
    basarisizListe({ state: 'passed', value: 3 });
    await ac();

    // Başlık hem kartta hem engel listesinde geçiyor; varlığı yeter.
    expect((await screen.findAllByText('Süt dolabı sıcaklığı')).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText('Açıklama')).toBeNull();
  });

  it('gönderim engeli maddenin kendisine götürüyor', async () => {
    basarisizListe();
    await ac();

    const bag = (await screen.findAllByRole('link', { name: 'Süt dolabı sıcaklığı' }))[0];
    expect(bag.getAttribute('href')).toBe('#madde-m-3');
  });

  it('dokunulmamış formda düğme “Kaydet” diyor, “Kaydedildi” yazmıyor (B09)', async () => {
    // Boş formun düğmesinde "kaydedildi" yazıyordu: ilk kez gelen
    // kullanıcı kaydın yapıldığını sanıyordu.
    cevapsizOlcum();
    await ac();

    expect(await screen.findByRole('button', { name: 'Kaydet' })).toBeTruthy();
    expect(screen.queryByText('Kaydedildi')).toBeNull();
  });

  it('kaydedilmiş ölçümde “Kaydedildi” yazıyor', async () => {
    basarisizListe({ state: 'passed', value: 3 });
    await ac();

    expect(await screen.findByText('Kaydedildi')).toBeTruthy();
  });

  it('aralık uyarısı yalnızca gerçekten dışarıdaki değerde çıkıyor (B09)', async () => {
    basarisizListe({ state: 'passed', value: 3 });
    await ac();

    expect(await screen.findByText('Kabul aralığı 0–4°C.')).toBeTruthy();
    expect(screen.queryByText(/bu değer dışarıda/)).toBeNull();
  });

  /** Ölçüm maddesi hiç cevaplanmamış liste. */
  function cevapsizOlcum() {
    gorunum.mockResolvedValue({
      ...CALISTIRMA,
      status: 'in_progress',
      writable_from: ACILIS,
      window_start: ACILIS,
      window_end: BITIS,
      tolerance_end: BITIS,
      sections: [
        {
          id: 's-1',
          title: 'Soğuk zincir',
          items: [
            madde({
              item_id: 'm-3',
              title: 'Süt dolabı sıcaklığı',
              type: 'temperature',
              min_value: 0,
              max_value: 4,
              unit: '°C',
              photo_required: true,
              answer: null,
            }),
          ],
        },
      ],
    } as unknown as CalistirmaGorunumu);
  }

  it('cevapsız ölçüm maddesinde fotoğraf önce cevap istiyor (BR-08a)', async () => {
    cevapsizOlcum();
    await ac();

    expect(await screen.findByText('Fotoğraf için önce cevabı kaydedin.')).toBeTruthy();
  });
});

describe('liste kartının bağlamı (bağımsız test turu B10)', () => {
  it('kartın başlığı liste adı, şube meta satırında', async () => {
    // İki kart da "Kadıköy" yazıyordu: hangi işin yapılacağı ancak
    // liste açılınca öğreniliyordu.
    bugun.mockResolvedValue([
      {
        id: 'r-1',
        plan_name: 'Günlük kapanış',
        branch_name: 'Kadıköy',
        status: 'scheduled',
        window_start: '2026-11-05T19:00:00Z',
        writable_from: '2026-11-05T18:45:00Z',
        window_end: '2026-11-05T22:30:00Z',
        tolerance_end: '2026-11-05T23:30:00Z',
      },
    ] as never);
    kur();

    expect(await screen.findByText('Günlük kapanış')).toBeTruthy();
    expect(screen.getByText(/Kadıköy/)).toBeTruthy();
  });

  it('gece yarısını aşan pencerede tarih de yazıyor', async () => {
    // Sahada "00:00–03:30" görünüyor, yönetici panosu aynı pencereyi
    // "08/11 00:00–03:30" diyordu.
    bugun.mockResolvedValue([
      {
        id: 'r-1',
        plan_name: 'Gece devri',
        branch_name: 'Kadıköy',
        status: 'scheduled',
        window_start: '2027-03-09T21:00:00Z',
        writable_from: '2027-03-09T20:45:00Z',
        window_end: '2027-03-10T00:30:00Z',
        tolerance_end: '2027-03-10T01:30:00Z',
      },
    ] as never);
    kur();

    const meta = await screen.findByText(/Pencere:/);
    expect(meta.textContent).toMatch(/\d{2}\/\d{2}/);
  });
});

describe('çalıştırma kilidi ekranda (BR-26 · FR-0521)', () => {
  // Kilit sunucuda hep vardı ama görünmüyordu: ikinci kişi yazmaya
  // çalışınca 409 alıyordu ve mesajda ham bir kimlik vardı.

  async function listeyiAc(ben: Ben | null) {
    kur(ben);
    await userEvent.click(await screen.findByRole('button', { name: 'Listeyi aç' }));
    await screen.findByText('Gaz vanası kapatıldı');
  }

  it('kilit boşken üstlenme düğmesi çıkıyor', async () => {
    await listeyiAc(PERSONEL);

    expect(screen.getByRole('button', { name: 'Listeyi üstlen' })).toBeInTheDocument();
  });

  it('kilit sendeyse bırakma düğmesi çıkıyor', async () => {
    gorunum.mockResolvedValue({ ...CALISTIRMA, locked_by: PERSONEL.id } as CalistirmaGorunumu);

    await listeyiAc(PERSONEL);

    expect(screen.getByText(/Liste sende/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Bırak' })).toBeInTheDocument();
  });

  it('başkasındaysa adını söylüyor, personele kaldırma düğmesi vermiyor', async () => {
    gorunum.mockResolvedValue({
      ...CALISTIRMA,
      locked_by: 'baskasi-1',
      locked_by_name: 'Emre Personel',
    } as CalistirmaGorunumu);

    await listeyiAc(PERSONEL);

    expect(screen.getByText('Emre Personel bu listeyi dolduruyor.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Kilidi kaldır' })).not.toBeInTheDocument();
  });

  it('müdür başkasının kilidini kaldırabiliyor', async () => {
    // Tek çıkış yolu 30 dakika beklemekti: personel eve gidince müdür
    // listeyi kurtaramıyordu.
    gorunum.mockResolvedValue({
      ...CALISTIRMA,
      locked_by: 'baskasi-1',
      locked_by_name: 'Emre Personel',
    } as CalistirmaGorunumu);

    await listeyiAc(SUBE_MUDURU);

    expect(screen.getByRole('button', { name: 'Kilidi kaldır' })).toBeInTheDocument();
  });
});
