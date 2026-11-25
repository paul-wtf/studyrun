import { render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

const here = vi.hoisted(() => ({ url: new URL('http://localhost/modules/3') }));
vi.mock('$app/state', () => ({ page: here }));

import Header from './Header.svelte';

describe('Header', () => {
  it('marks the section of the current page', () => {
    render(Header);
    expect(screen.getByRole('link', { name: 'Module' })).toHaveAttribute('aria-current', 'page');
    for (const name of ['Start', 'Plan', 'Fächer', 'Gemeldet', 'Kosten']) {
      expect(screen.getByRole('link', { name })).not.toHaveAttribute('aria-current');
    }
  });

  it('marks Start only on the start page', () => {
    here.url = new URL('http://localhost/');
    render(Header);
    expect(screen.getByRole('link', { name: 'Start' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Module' })).not.toHaveAttribute('aria-current');
  });

  it('links Start, Plan, Fächer, Module, Gemeldet and Kosten in that order', () => {
    render(Header);
    const nav = screen.getByRole('navigation', { name: 'Hauptnavigation' });
    expect([...nav.querySelectorAll('a')].map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
      ['Start', '/'],
      ['Plan', '/plan'],
      ['Fächer', '/subjects'],
      ['Module', '/modules'],
      ['Gemeldet', '/flags'],
      ['Kosten', '/costs']
    ]);
  });

  it('marks Fächer on a subject page', () => {
    here.url = new URL('http://localhost/subjects/2');
    render(Header);
    expect(screen.getByRole('link', { name: 'Fächer' })).toHaveAttribute('aria-current', 'page');
  });
});
