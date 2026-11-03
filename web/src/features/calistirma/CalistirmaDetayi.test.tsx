import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { calistirmaGorunumu, calistirmaPdf, type CalistirmaGorunumu } from '../../api/calistirma';
import { dosyayiIndir } from '../../api/raporlar';
import { calistirmaKanitlari, kanitBaglantisi, type Kanit } from '../../api/kanitlar';
import { CalistirmaDetayi } from './CalistirmaDetayi';

vi.mock('../../api/calistirma');
vi.mock('../../api/kanitlar');
vi.mock('../../api/raporlar');
const getir = vi.mocked(calistirmaGorunumu);
const kanitlariGetir = vi.mocked(calistirmaKanitlari);
const baglantiGetir = vi.mocked(kanitBaglantisi);
const pdfGetir = vi.mocked(calistirmaPdf);
const indir = vi.mocked(dosyayiIndir);

const KANIT: Kanit = {
  id: 'k-1',
  run_id: 'r-1',
  answer_id: 'c-1',
  item_id: 'i-1',
  status: 'stored',
  content_type: 'image/jpeg',
  size_bytes: 250_000,
  sha256: 'a'.repeat(64),
  has_stamp: true,
  has_thumbnail: true,
  created_at: '2026-11-02T21:30:00Z',
  captured_at: '2026-11-02T21:29:00Z',
  distance_meters: 1800,
  flags: [{ code: 'far_location', label: 'Konum şube dışında' }],
};

const MADDE = {
  type_label: 'Onay',
  required: true,
  photo_required: false,
  critical: false,
  min_value: null,
  max_value: null,
  unit: null,
};

const GORUNUM: CalistirmaGorunumu = {
  run_id: 'r-1',
  branch_id: 'b-1',
  branch_name: 'Kadıköy',
  region_name: 'Anadolu',
  business_day: '2026-11-02',
  status: 'submitted',
  result: 'failed',
  score_percent: 71,
  window_start: '2026-11-02T19:00:00Z',
  window_end: '2026-11-02T22:30:00Z',
  tolerance_end: '2026-11-02T22:30:00Z',
  submitted_at: '2026-11-02T21:40:00Z',
  template_name: 'Kapanış (kafe)',
  locked_by: null,
  sections: [
    {
      id: 's-1',
      title: 'Mutfak',
      items: [
        {
          ...MADDE,
          item_id: 'i-0',
          title: 'Kapanış sırası',
          type: 'instruction',
          type_label: 'Talimat',
          answer: null,
        },
        {
          ...MADDE,
          item_id: 'i-1',
          title: 'Espresso makinesi geri yıkama',
          type: 'confirm',
          answer: {
            id: 'a-1',
            item_id: 'i-1',
            state: 'passed',
            value: null,
            note: null,
            evidence_count: 0,
            answered_at: '2026-11-02T21:00:00Z',
            clock_skew_minutes: 0,
            clock_flagged: false,
          },
        },
        {
          ...MADDE,
          item_id: 'i-2',
          title: 'Süt dolabı sıcaklığı',
          type: 'temperature',
          type_label: 'Sıcaklık',
          critical: true,
          answer: {
            id: 'a-2',
            item_id: 'i-2',
            state: 'failed',
            value: 9,
            note: 'Sıcaklık 9 derece, teknisyen çağrıldı',
            evidence_count: 1,
            answered_at: '2026-11-02T21:05:00Z',
            clock_skew_minutes: 40,
            clock_flagged: true,
          },
        },
        {
          ...MADDE,
          item_id: 'i-3',
          title: 'Cevapsız madde',
          type: 'confirm',
          answer: null,
        },
        {
          ...MADDE,
          item_id: 'i-4',
          title: 'Zemin paspası',
          type: 'confirm',
          answer: {
            id: 'a-4',
            item_id: 'i-4',
            state: 'not_done',
            value: null,
            note: null,
            evidence_count: 0,
            answered_at: '2026-11-02T21:10:00Z',
            clock_skew_minutes: 0,
            clock_flagged: false,
            not_done_reason: 'no_material',
            not_done_reason_label: 'Malzeme yok',
          },
        },
      ],
    },
  ],
  blockers: [{ item_id: 'i-3', title: 'Cevapsız madde', kind: 'unanswered' }],
};

function kur(onKapat = vi.fn()) {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={istemci}>
      <CalistirmaDetayi runId="r-1" onKapat={onKapat} />
    </QueryClientProvider>,
  );
  return onKapat;
}

beforeEach(() => {
  vi.resetAllMocks();
  getir.mockResolvedValue(GORUNUM);
  kanitlariGetir.mockResolvedValue([]);
  baglantiGetir.mockResolvedValue('/api/v1/evidence/file/belirtec');
});

describe('Çalıştırma detayı', () => {
  it('puan ve sonuç başlıkta gösterilir', async () => {
    kur();
    expect(await screen.findByRole('heading', { name: /Kadıköy/ })).toBeInTheDocument();
    expect(screen.getByText('%71')).toBeInTheDocument();
    expect(screen.getByText('Başarısız')).toBeInTheDocument();
  });

  it('başlık hangi şubeye ait olduğunu söyler', async () => {
    // Kart panoda ızgaranın altında açılıyor: şube adı yoksa üç şubenin
    // kartı birbirinin aynısı görünüyor.
    kur();

    const baslik = await screen.findByRole('heading', { name: /Kadıköy/ });

    expect(baslik).toHaveTextContent('Kadıköy');
    expect(baslik).toHaveTextContent('Anadolu');
    expect(screen.getByText(/Kapanış \(kafe\)/)).toHaveTextContent('2 Kasım 2026');
  });

  it('cevap durumları, kanıt sayısı ve not gösterilir', async () => {
    kur();
    await screen.findByRole('heading', { name: /Kadıköy/ });

    expect(screen.getAllByText('Geçti')).toHaveLength(1);
    expect(screen.getByText('Geçmedi')).toBeInTheDocument();
    expect(screen.getByText('Sıcaklık 9 derece, teknisyen çağrıldı')).toBeInTheDocument();
    expect(screen.getByText('Cevapsız')).toBeInTheDocument();
  });

  it('talimat satırı cevap beklemez', async () => {
    kur();
    await screen.findByRole('heading', { name: /Kadıköy/ });
    const satir = screen.getByText('Kapanış sırası').closest('li');
    expect(satir).toHaveTextContent('Talimat');
    expect(satir).not.toHaveTextContent('Cevapsız');
  });

  it('cihaz saati sapması işaretlenir', async () => {
    kur();
    await screen.findByRole('heading', { name: /Kadıköy/ });
    expect(screen.getByText('cihaz saati')).toBeInTheDocument();
  });

  it('gönderime engel eksikler listelenir', async () => {
    kur();
    expect(await screen.findByText(/Gönderime engel eksikler/)).toBeInTheDocument();
    expect(screen.getByText(/cevaplanmadı/)).toBeInTheDocument();
  });

  it('kapat düğmesi geri çağırır', async () => {
    const onKapat = kur();
    await screen.findByRole('heading', { name: /Kadıköy/ });
    await userEvent.click(screen.getByRole('button', { name: 'Kapat' }));
    expect(onKapat).toHaveBeenCalled();
  });

  it('yapılamadı sebebi madde yanında yazılı', async () => {
    // Sebep kodu değil etiketi gösterilir; renk tek başına yetmez.
    kur();

    expect(await screen.findByText('Malzeme yok')).toBeInTheDocument();
  });

  it('kanıt görseli imzalı bağlantıyla gösterilir', async () => {
    kanitlariGetir.mockResolvedValue([KANIT]);

    kur();

    const gorsel = await screen.findByAltText('Kanıt fotoğrafı');
    expect(gorsel).toHaveAttribute('src', '/api/v1/evidence/file/belirtec');
    // Izgara küçük resmi ister; damgalı kopya tıklamayla gelir (FR-0606).
    expect(baglantiGetir).toHaveBeenCalledWith('k-1', 'thumbnail');
  });

  it('kanıt bayrağı metniyle birlikte gösterilir', async () => {
    // Bayrak suçlama değil, incelemeye çağrı: renk tek başına yetmez.
    kanitlariGetir.mockResolvedValue([KANIT]);

    kur();

    expect(await screen.findByText('Konum şube dışında')).toBeInTheDocument();
  });

  it('yüklenmemiş kanıt gösterilmez', async () => {
    // "pending" bir niyet beyanı: baytları depoda değil, görseli yok.
    kanitlariGetir.mockResolvedValue([{ ...KANIT, status: 'pending' }]);

    kur();

    await screen.findByRole('heading', { name: /Kadıköy/ });
    expect(screen.queryByAltText('Kanıt fotoğrafı')).not.toBeInTheDocument();
  });

  it('damgasız kanıt bunu söyler', async () => {
    // Damgalama turlu bir iş: hazır olmadığında kullanıcı bilsin.
    kanitlariGetir.mockResolvedValue([{ ...KANIT, has_stamp: false }]);

    kur();

    expect(await screen.findByText('Damga bekliyor')).toBeInTheDocument();
  });

  it('açılamayan görsel kırık simge değil metin gösterir', async () => {
    kanitlariGetir.mockResolvedValue([KANIT]);

    kur();

    const gorsel = await screen.findByAltText('Kanıt fotoğrafı');
    fireEvent.error(gorsel);

    expect(await screen.findByText('Görsel açılamadı')).toBeInTheDocument();
  });

  it('bayraksız kanıt bunu açıkça söyler', async () => {
    kanitlariGetir.mockResolvedValue([{ ...KANIT, flags: [] }]);

    kur();

    expect(await screen.findByText('Bayrak yok')).toBeInTheDocument();
  });

  it('çalıştırma PDF olarak indirilir', async () => {
    pdfGetir.mockResolvedValue(new Blob([new Uint8Array([37, 80, 68, 70])]));

    kur();
    await screen.findByRole('heading', { name: /Kadıköy/ });
    await userEvent.click(screen.getByRole('button', { name: 'PDF indir' }));

    expect(pdfGetir).toHaveBeenCalledWith('r-1');
    expect(indir).toHaveBeenCalledWith(expect.any(Blob), expect.stringContaining('.pdf'));
  });

  it('PDF üretilemezse hata görünür, sayfa durur', async () => {
    pdfGetir.mockRejectedValue(new Error('500'));

    kur();
    await screen.findByRole('heading', { name: /Kadıköy/ });
    await userEvent.click(screen.getByRole('button', { name: 'PDF indir' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('PDF üretilemedi');
    expect(indir).not.toHaveBeenCalled();
  });

  it('listelenmeyen engelleri sayıyla söyler', async () => {
    /* Başlık "(9)" deyip altta altı satır göstermek, sayan kişiyi
       kendi gözünden şüphe ettiriyordu. */
    getir.mockResolvedValue({
      ...GORUNUM,
      blockers: Array.from({ length: 9 }, (_, i) => ({
        item_id: `i-${i}`,
        title: `Eksik ${i}`,
        kind: 'unanswered' as const,
      })),
    });

    kur();

    expect(await screen.findByText(/ve 3 eksik daha/)).toBeInTheDocument();
  });
});
