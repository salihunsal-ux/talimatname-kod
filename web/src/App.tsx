import { QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';

import { sorguIstemcisi } from './api/sorguIstemcisi';
import { Kabuk } from './bilesenler/Kabuk';
import { SistemDurumu } from './features/sistem/SistemDurumu';
import { SubelerSayfasi } from './features/subeler/SubelerSayfasi';

export type Bolum = 'subeler' | 'sistem';

export function App() {
  const [bolum, setBolum] = useState<Bolum>('subeler');

  return (
    <QueryClientProvider client={sorguIstemcisi}>
      <Kabuk bolum={bolum} onBolum={setBolum}>
        {bolum === 'subeler' ? <SubelerSayfasi /> : <SistemDurumu />}
      </Kabuk>
    </QueryClientProvider>
  );
}
