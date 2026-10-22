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
    henuzYok: 'Bu bölüm henüz geliştirilmedi',
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
  genel: {
    yukleniyor: 'Yükleniyor…',
  },
  subeler: {
    baslik: 'Şubeler',
    pasifleriGoster: 'Pasifleri göster',
    pasif: 'Pasif',
    gunKisaltma: 'gün açık',
    secimYok: 'Soldan bir şube seçin.',
    calismaSaatleri: 'Çalışma saatleri',
    kapali: 'Kapalı',
    istasyonlar: 'İstasyonlar',
    pasiflestir: 'Şubeyi pasifleştir',
    pasiflestirmeNotu:
      'Pasifleştirme silme değildir: geçmiş çalıştırmalar ve kanıtlar durur, yeni çalıştırma üretilmez.',
    kod: 'Kod',
    ad: 'Ad',
    ekle: 'Şube ekle',
  },
  personel: {
    baslik: 'Personel ve roller',
    sube: 'Şube',
    bolge: 'Bölge',
    rol: 'Rol',
    rolKapsam: 'Rol ve kapsam',
    hepsi: 'Hepsi',
    seciniz: 'Seçiniz',
    pasifleriGoster: 'Pasif ve maskelileri göster',
    pasif: 'Pasif',
    maskeli: 'Maskeli',
    bos: 'Bu süzgeçle kayıt yok.',
    ad: 'Ad soyad',
    telefon: 'Telefon',
    islem: 'İşlem',
    pasiflestir: 'Pasifleştir',
    maskele: 'Maskele',
    maskeleOnay: 'Maskelemeyi onayla',
    davet: 'Davet et',
    davetKuyrukta: "Kayıt açıldı. Davet SMS'i, sağlayıcı bağlanınca gönderilecek (ST-044).",
    bilinmeyenKapsam: 'kapsam bulunamadı',
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
