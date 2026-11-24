import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import SessionExpired from './SessionExpired.svelte';

describe('SessionExpired', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('reloads the page on Neu anmelden', async () => {
    const reload = vi.fn();
    vi.stubGlobal('location', { ...window.location, reload });
    render(SessionExpired);
    await userEvent.click(screen.getByRole('button', { name: 'Neu anmelden' }));
    expect(reload).toHaveBeenCalled();
  });
});
