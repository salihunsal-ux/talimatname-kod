import { QueryClientProvider, useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { belirtecAl, benGetir, cikisYap } from './api/oturum';
import { sorguIstemcisi } from './api/sorguIstemcisi';
import { OturumBaglami } from './api/yetki';
import { Kabuk } from './bilesenler/Kabuk';
import { SistemDurumu } from './features/sistem/SistemDurumu';
import { AksiyonlarSayfasi } from './features/aksiyonlar/AksiyonlarSayfasi';
import { BildirimlerSayfasi } from './features/bildirimler/BildirimlerSayfasi';
import { GirisSayfasi } from './features/oturum/GirisSayfasi';
import { PanoSayfasi } from './features/pano/PanoSayfasi';
import { PersonelSayfasi } from './features/personel/PersonelSayfasi';
import { PlanlarSayfasi } from './features/planlar/PlanlarSayfasi';
import { KurulumSayfasi } from './features/kurulum/KurulumSayfasi';
import { SablonlarSayfasi } from './features/sablonlar/SablonlarSayfasi';
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
  | 'sistem';

export function App() {
  return (
    <QueryClientProvider client={sorguIstemcisi}>
      <Kapi />
    </QueryClientProvider>
  );
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
            {bolum === 'kurulum' && <KurulumSayfasi />}
            {bolum === 'sistem' && <SistemDurumu />}
          </>
        )}
      </Kabuk>
    </OturumBaglami>
  );
}
