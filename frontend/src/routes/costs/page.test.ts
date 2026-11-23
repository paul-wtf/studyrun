import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/svelte';
import Page from './+page.svelte';
import { mockApi } from '#lib/test/mockApi.ts';

const COSTS = {
  today: { total: 0.35, by_feature: { generate: 0.2, verify: 0.05, grade: 0.1, tutor: 0 } },
  month: { total: 4.5, by_feature: { generate: 3, verify: 1, grade: 0.4, tutor: 0.1 } },
  cap_today: 0.5,
  remaining_today: 0.4,
  generation_budget_today: 10,
  generation_remaining_today: 9.75
};

describe('costs page', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('renders the numbers by feature', async () => {
    mockApi({ 'GET /api/costs': COSTS });
    render(Page);
    const today = await screen.findByRole('region', { name: 'Heute' });
    expect(within(today).getByText('0,35 $')).toBeInTheDocument();
    expect(within(today).getByText('Erzeugung').nextElementSibling).toHaveTextContent('0,20 $');
    expect(within(today).getByText('Prüfung').nextElementSibling).toHaveTextContent('0,05 $');
    expect(within(today).getByText('Bewertung').nextElementSibling).toHaveTextContent('0,10 $');
    expect(within(today).getByText('Tutor').nextElementSibling).toHaveTextContent('0,00 $');
    const month = screen.getByRole('region', { name: 'Dieser Monat' });
    expect(within(month).getByText('4,50 $')).toBeInTheDocument();
    expect(within(month).getByText('Erzeugung').nextElementSibling).toHaveTextContent('3,00 $');
    expect(screen.getByText(/Tageslimit/).parentElement).toHaveTextContent('0,50 $');
    expect(screen.getByText(/Tageslimit/).parentElement).toHaveTextContent('0,40 $');
    expect(screen.getByText(/Erzeugungsbudget/).parentElement).toHaveTextContent('10,00 $');
    expect(screen.getByText(/Erzeugungsbudget/).parentElement).toHaveTextContent('9,75 $');
  });
});
