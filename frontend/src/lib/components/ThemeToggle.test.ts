import { beforeEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import { get } from 'svelte/store';
import ThemeToggle from './ThemeToggle.svelte';
import { theme } from '#lib/stores/theme.ts';

describe('ThemeToggle', () => {
  beforeEach(() => theme.set('mocha'));

  it('offers the light design in mocha and toggles on click', async () => {
    render(ThemeToggle);
    await userEvent.click(screen.getByRole('button', { name: 'Helles Design' }));
    expect(get(theme)).toBe('latte');
    expect(screen.getByRole('button', { name: 'Dunkles Design' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Dunkles Design' }));
    expect(get(theme)).toBe('mocha');
  });
});
