import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { TEMA_ANAHTARI } from '../tema';
import { TemaSecici } from './Tema';

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-tema');
});

describe('TemaSecici', () => {
  it('seçilen tema belgeye ve depoya yazılıyor', async () => {
    render(<TemaSecici />);

    const secici = screen.getByLabelText('Tema');
    expect(secici).toHaveValue('sistem');

    await userEvent.selectOptions(secici, 'koyu');

    expect(document.documentElement.getAttribute('data-tema')).toBe('koyu');
    expect(localStorage.getItem(TEMA_ANAHTARI)).toBe('koyu');
  });

  it('kayıtlı seçimle açılıyor', () => {
    localStorage.setItem(TEMA_ANAHTARI, 'acik');

    render(<TemaSecici />);

    expect(screen.getByLabelText('Tema')).toHaveValue('acik');
  });
});
