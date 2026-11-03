import { useEffect, useState } from 'react';

/**
 * Kısa istekte hiçbir şey görünmesin: iskeletin bir an parlayıp
 * kaybolması, hiç göstermemekten kötü. Varsayılan 250 ms — bunun
 * altındaki yanıtlar ekranda iz bırakmıyor.
 */
export function useGecikme(ms = 250): boolean {
  const [gecti, setGecti] = useState(false);

  useEffect(() => {
    const sayac = setTimeout(() => setGecti(true), ms);
    return () => clearTimeout(sayac);
  }, [ms]);

  return gecti;
}
