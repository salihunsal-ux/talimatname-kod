import { QueryClientProvider } from '@tanstack/react-query';

import { sorguIstemcisi } from './api/sorguIstemcisi';
import { Kabuk } from './bilesenler/Kabuk';
import { SistemDurumu } from './features/sistem/SistemDurumu';

export function App() {
  return (
    <QueryClientProvider client={sorguIstemcisi}>
      <Kabuk>
        <SistemDurumu />
      </Kabuk>
    </QueryClientProvider>
  );
}
