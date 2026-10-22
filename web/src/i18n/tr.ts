/**
 * Arayüz metinleri (FR-1803). Tek dil (Türkçe) ama metin **koda gömülmez**:
 * v1.1'de başka dil eklenecekse buraya bakılır, bileşenlere değil.
 */
export const tr = {
  uygulama: {
    ad: 'Talimatname',
    aciklama: 'Kanıtlı görev listesi',
  },
  gezinme: {
    pano: 'Pano',
    subeler: 'Şubeler',
    personel: 'Personel',
    sablonlar: 'Şablonlar',
    planlar: 'Planlar',
    aksiyonlar: 'Aksiyonlar',
    raporlar: 'Raporlar',
  },
  sistem: {
    baslik: 'Sistem durumu',
    saglikli: 'API çalışıyor',
    ulasilamiyor: 'API ulaşılamıyor',
    yukleniyor: 'Kontrol ediliyor…',
    surum: 'Sürüm',
    ortam: 'Ortam',
    veritabani: 'Veritabanı',
    nesneDepo: 'Nesne depolama',
    yapilandirilmis: 'yapılandırılmış',
    yapilandirilmamis: 'yapılandırılmamış',
    yenile: 'Yeniden dene',
  },
  durum: {
    planli: 'Planlı',
    devam: 'Devam ediyor',
    tamamlandi: 'Tamamlandı',
    gec: 'Geç tamamlandı',
    kacirildi: 'Kaçırıldı',
    yapilmayacak: 'Yapılmayacak',
  },
  hata: {
    genel: 'Bir şey ters gitti',
    aglaBaglanilamadi: 'Sunucuya bağlanılamadı',
  },
} as const;

export type Metinler = typeof tr;
