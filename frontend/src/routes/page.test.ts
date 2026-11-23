import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import Page from './+page.svelte';
import { mockApi } from '#lib/test/mockApi.ts';

const COSTS = {
  today: { total: 0.12, by_feature: { generate: 0, verify: 0, grade: 0.1, tutor: 0.02 } },
  cap_today: 0.5
};
const MODULES = [{ id: 1, name: 'Bio', position: 0, booklets: [{ chapters: { ready: 3 } }] }];

const BASE = { 'GET /api/costs': COSTS, 'GET /api/modules': MODULES, 'GET /api/runs/current': { run: null } };

describe('home', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('offers to start a run and shows the spend', async () => {
    mockApi({ ...BASE });
    render(Page);
    expect(await screen.findByRole('link', { name: 'Run starten' })).toHaveAttribute('href', '/run');
    expect(screen.getByText(/0,12/)).toBeInTheDocument();
    expect(screen.getByText(/0,50/)).toBeInTheDocument();
  });

  it('keeps generation spend apart from the grading cap', async () => {
    mockApi({
      ...BASE,
      'GET /api/costs': {
        today: { total: 4.12, by_feature: { generate: 3, verify: 1, grade: 0.1, tutor: 0.02 } },
        cap_today: 0.5
      }
    });
    render(Page);
    expect(await screen.findByText('Bewertung heute: 0,12 von 0,50 $')).toBeInTheDocument();
    expect(screen.getByText('Erzeugung heute: 4,00 $')).toBeInTheDocument();
    expect(screen.queryByText(/4,12/)).not.toBeInTheDocument();
  });

  it('leaves out the generation line when nothing was generated', async () => {
    mockApi({ ...BASE });
    render(Page);
    expect(await screen.findByText('Bewertung heute: 0,12 von 0,50 $')).toBeInTheDocument();
    expect(screen.queryByText(/Erzeugung/)).not.toBeInTheDocument();
  });

  it('offers to resume a run started today', async () => {
    mockApi({
      'GET /api/costs': COSTS,
      'GET /api/modules': MODULES,
      'GET /api/runs/current': { run: { id: 4, entries: [{ n: 0 }] } }
    });
    render(Page);
    expect(await screen.findByRole('link', { name: 'Run fortsetzen' })).toBeInTheDocument();
  });

  it('links to the modules when nothing is ready to study', async () => {
    mockApi({ ...BASE, 'GET /api/modules': [] });
    render(Page);
    expect(await screen.findByRole('link', { name: /Module/ })).toHaveAttribute('href', '/modules');
    expect(screen.queryByRole('link', { name: 'Run starten' })).not.toBeInTheDocument();
  });
});
