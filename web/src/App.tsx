import { QueryClientProvider, useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { belirtecAl, benGetir, cikisYap } from './api/oturum';
import { sorguIstemcisi } from './api/sorguIstemcisi';
import { mudurMu, OturumBaglami } from './api/yetki';
import { Kabuk } from './bilesenler/Kabuk';
import { SistemDurumu } from './features/sistem/SistemDurumu';
import { DogrulamaSayfasi } from './features/dogrulama/DogrulamaSayfasi';
import { AksiyonlarSayfasi } from './features/aksiyonlar/AksiyonlarSayfasi';
import { BildirimlerSayfasi } from './features/bildirimler/BildirimlerSayfasi';
import { GirisSayfasi } from './features/oturum/GirisSayfasi';
import { PanoSayfasi } from './features/pano/PanoSayfasi';
import { PersonelSayfasi } from './features/personel/PersonelSayfasi';
import { PlanlarSayfasi } from './features/planlar/PlanlarSayfasi';
import { KurulumSayfasi } from './features/kurulum/KurulumSayfasi';
import { RaporlarSayfasi } from './features/raporlar/RaporlarSayfasi';
import { SablonlarSayfasi } from './features/sablonlar/SablonlarSayfasi';
import { SahaSayfasi } from './features/saha/SahaSayfasi';
import { SubelerSayfasi } from './features/subeler/SubelerSayfasi';
import { tr } from './i18n/tr';

export type Bolum =
  | 'pano'
  | 'subeler'
  | 'personel'
  | 'sablonlar'
  | 'planlar'
  | 'aksiyonlar'
  | 'bildirimler'
  | 'kurulum'
  | 'raporlar'
  | 'saha'
  | 'sistem';

/** Oturumsuz sayfanın yolu. PDF dipnotundaki adres de burayı gösteriyor. */
const DOGRULAMA_YOLU = '/dogrula';

export function App() {
  const belgeKodu = dogrulamaKodu();
  return (
    <QueryClientProvider client={sorguIstemcisi}>
      {belgeKodu === null ? <Kapi /> : <DogrulamaSayfasi kod={belgeKodu} />}
    </QueryClientProvider>
  );
}

/**
 * Yol `/dogrula` ise oturum kapısı **atlanır**: belgeyi doğrulayan
 * denetçi kullanıcı değil, girişi yok (FR-1218). Dönen değer: yol
 * başka bir şeyse null, kod verilmemişse boş dize.
 *
 * Tam bir yönlendirici (router) kurulmadı: panelin geri kalanı bölüm
 * durumuyla geziniyor ve tek bir oturumsuz sayfa için bütün gezinmeyi
 * değiştirmek kazancından büyük olurdu. Derin bağlantı çalışıyor çünkü
 * Caddy bilinmeyen yolu index.html'e düşürüyor (infra/Caddyfile).
 */
function dogrulamaKodu(): string | null {
  const yol = window.location.pathname.replace(/\/+$/, '') || '/';
  if (yol === DOGRULAMA_YOLU) return '';
  if (!yol.startsWith(DOGRULAMA_YOLU + '/')) return null;
  return decodeURIComponent(yol.slice(DOGRULAMA_YOLU.length + 1));
}

/**
 * Oturum kapısı: belirteç yoksa giriş, varsa panel.
 *
 * Kullanıcı bilgisi her açılışta `/auth/me` ile **sunucudan** okunuyor;
 * elde eski bir belirteç kalmışsa (süresi dolmuş ya da kullanıcı pasife
 * alınmış) burada anlaşılır ve oturum düşer: yetki belirtece değil
 * kullanıcıya bağlı (FR-0205).
 */
function Kapi() {
  const [belirtec, setBelirtec] = useState<string | null>(() => belirtecAl());
  const [bolum, setBolum] = useState<Bolum>('pano');

  const ben = useQuery({
    queryKey: ['ben', belirtec],
    queryFn: benGetir,
    enabled: belirtec !== null,
    retry: false,
  });

  function giris() {
    setBelirtec(belirtecAl());
  }

  function cik() {
    cikisYap();
    sorguIstemcisi.clear();
    setBelirtec(null);
  }

  // Belirteç yok ya da sunucu kabul etmedi: giriş ekranı.
  if (belirtec === null || ben.isError) {
    if (ben.isError) cikisYap();
    return <GirisSayfasi onGiris={giris} />;
  }

  // Personelin panel ekranı yok (rol matrisi) ama işi var: saha
  // istemcisi. Önce burada "panel müdürler için" yazan bir kart
  // duruyordu; personel giriş yapıp hiçbir şey yapamıyordu.
  if (ben.data && !mudurMu(ben.data)) {
    return (
      <OturumBaglami value={ben.data}>
        <Kabuk
          menusuz
          bolum="saha"
          onBolum={() => undefined}
          kullanici={{ ad: ben.data.full_name, rol: ben.data.roles[0]?.role_label ?? '' }}
          onCikis={cik}
        >
          <SahaSayfasi />
        </Kabuk>
      </OturumBaglami>
    );
  }

  return (
    <OturumBaglami value={ben.data ?? null}>
      <Kabuk
        bolum={bolum}
        onBolum={setBolum}
        kullanici={ben.data && { ad: ben.data.full_name, rol: ben.data.roles[0]?.role_label ?? '' }}
        onCikis={cik}
      >
        {ben.isPending ? (
          <p role="status" style={{ color: 'var(--renk-sessiz)' }}>
            {tr.genel.yukleniyor}
          </p>
        ) : (
          <>
            {bolum === 'pano' && <PanoSayfasi />}
            {bolum === 'subeler' && <SubelerSayfasi />}
            {bolum === 'personel' && <PersonelSayfasi />}
            {bolum === 'sablonlar' && <SablonlarSayfasi />}
            {bolum === 'planlar' && <PlanlarSayfasi />}
            {bolum === 'aksiyonlar' && <AksiyonlarSayfasi />}
            {bolum === 'bildirimler' && <BildirimlerSayfasi />}
            {bolum === 'raporlar' && <RaporlarSayfasi />}
            {bolum === 'saha' && <SahaSayfasi />}
            {bolum === 'kurulum' && <KurulumSayfasi />}
            {bolum === 'sistem' && <SistemDurumu />}
          </>
        )}
      </Kabuk>
    </OturumBaglami>
  );
}
