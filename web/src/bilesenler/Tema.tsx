import { useState } from 'react';

import { tr } from '../i18n/tr';
import { TEMALAR, temaOku, temaYaz, type Tema } from '../tema';

/**
 * Tema seçici. Üç durumlu: "Sistem" cihazın tercihini izler, diğer
 * ikisi onu ezer. Açılır liste çünkü bu bir eylem değil bir **ayar**;
 * düğme dizisi bandı şişiriyordu.
 */
export function TemaSecici() {
  const [tema, setTema] = useState<Tema>(() => temaOku());

  return (
    <select
      className="alan tema-secici"
      aria-label={tr.tema.etiket}
      value={tema}
      onChange={(olay) => {
        const yeni = olay.target.value as Tema;
        setTema(yeni);
        temaYaz(yeni);
      }}
    >
      {TEMALAR.map((secenek) => (
        <option key={secenek} value={secenek}>
          {tr.tema[secenek]}
        </option>
      ))}
    </select>
  );
}
