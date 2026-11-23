import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import Page from './+page.svelte';
import { mockApi } from '#lib/test/mockApi.ts';

const COSTS = { today: { total: 0.12 }, cap_today: 0.5 };
const MODULES = [{ id: 1, name: 'Bio', position: 0, booklets: [{ chapters: { ready: 3 } }] }];

describe('home', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it('offers to start a run and shows the spend', async () => {
    mockApi({ 'GET /api/costs': COSTS, 'GET /api/modules': MODULES });
    render(Page);
    expect(await screen.findByRole('link', { name: 'Run starten' })).toHaveAttribute('href', '/run');
    expect(screen.getByText(/0,12/)).toBeInTheDocument();
    expect(screen.getByText(/0,50/)).toBeInTheDocument();
  });

  it('offers to resume a run started today', async () => {
    const now = new Date();
    const date = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    localStorage.setItem('studyrun.run', JSON.stringify({ id: 4, date }));
    mockApi({ 'GET /api/costs': COSTS, 'GET /api/modules': MODULES });
    render(Page);
    expect(await screen.findByRole('link', { name: 'Run fortsetzen' })).toBeInTheDocument();
  });

  it('links to the modules when nothing is ready to study', async () => {
    mockApi({ 'GET /api/costs': COSTS, 'GET /api/modules': [] });
    render(Page);
    expect(await screen.findByRole('link', { name: /Module/ })).toHaveAttribute('href', '/modules');
    expect(screen.queryByRole('link', { name: 'Run starten' })).not.toBeInTheDocument();
  });
});
