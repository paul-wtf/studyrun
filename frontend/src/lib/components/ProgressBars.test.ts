import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import ProgressBars from './ProgressBars.svelte';

describe('ProgressBars', () => {
  it('shows introduced and solid as two bars in percent', () => {
    render(ProgressBars, { introduced: 0.625, solid: 0.2 });
    expect(screen.getByRole('progressbar', { name: 'Eingeführt' })).toHaveAttribute('aria-valuenow', '63');
    expect(screen.getByRole('progressbar', { name: 'Gefestigt' })).toHaveAttribute('aria-valuenow', '20');
    expect(screen.getByText('63 %')).toBeInTheDocument();
  });
});
