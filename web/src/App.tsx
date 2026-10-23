import { QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';

import { sorguIstemcisi } from './api/sorguIstemcisi';
import { Kabuk } from './bilesenler/Kabuk';
import { SistemDurumu } from './features/sistem/SistemDurumu';
import { AksiyonlarSayfasi } from './features/aksiyonlar/AksiyonlarSayfasi';
import { PanoSayfasi } from './features/pano/PanoSayfasi';
import { PersonelSayfasi } from './features/personel/PersonelSayfasi';
import { PlanlarSayfasi } from './features/planlar/PlanlarSayfasi';
import { SablonlarSayfasi } from './features/sablonlar/SablonlarSayfasi';
import { SubelerSayfasi } from './features/subeler/SubelerSayfasi';

export type Bolum =
  'pano' | 'subeler' | 'personel' | 'sablonlar' | 'planlar' | 'aksiyonlar' | 'sistem';

export function App() {
  const [bolum, setBolum] = useState<Bolum>('pano');

  return (
    <QueryClientProvider client={sorguIstemcisi}>
      <Kabuk bolum={bolum} onBolum={setBolum}>
        {bolum === 'pano' && <PanoSayfasi />}
        {bolum === 'subeler' && <SubelerSayfasi />}
        {bolum === 'personel' && <PersonelSayfasi />}
        {bolum === 'sablonlar' && <SablonlarSayfasi />}
        {bolum === 'planlar' && <PlanlarSayfasi />}
        {bolum === 'aksiyonlar' && <AksiyonlarSayfasi />}
        {bolum === 'sistem' && <SistemDurumu />}
      </Kabuk>
    </QueryClientProvider>
  );
}
