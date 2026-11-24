import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/svelte';
import WeekDots from './WeekDots.svelte';

const days = (done: boolean[]) =>
  done.map((d, i) => ({ date: `2026-11-${String(23 + i).padStart(2, '0')}`, done: d }));

describe('WeekDots', () => {
  it('shows a dot per day from Monday to Sunday and the count towards the goal', () => {
    render(WeekDots, { week: { days: days([true, false, true, false, false, false, false]), goal: 4, done_count: 2 } });
    const list = screen.getByRole('list', { name: 'Diese Woche' });
    const items = within(list).getAllByRole('listitem');
    expect(items.map((li) => within(li).getByText(/: (gelernt|offen)$/).textContent)).toEqual([
      'Mo: gelernt', 'Di: offen', 'Mi: gelernt', 'Do: offen', 'Fr: offen', 'Sa: offen', 'So: offen'
    ]);
    expect(items.every((li) => !li.hasAttribute('aria-label'))).toBe(true);
    expect(screen.getByText('2 von 4 Tagen')).toBeInTheDocument();
  });

  it('says when the weekly goal is reached', () => {
    render(WeekDots, { week: { days: days([true, true, true, true, false, false, false]), goal: 4, done_count: 4 } });
    expect(screen.getByText('Wochenziel erreicht')).toBeInTheDocument();
  });
});
