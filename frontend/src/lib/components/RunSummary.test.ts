import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import RunSummary from './RunSummary.svelte';

describe('RunSummary', () => {
  it('shows the totals and a link home', () => {
    render(RunSummary, {
      props: {
        summary: { answered: 5, correct: 3, chapters_introduced: ['Die Zelle'], due_tomorrow: 4 }
      }
    });
    expect(screen.getByText('3 von 5 richtig')).toBeInTheDocument();
    expect(screen.getByText('Die Zelle')).toBeInTheDocument();
    expect(screen.getByText(/4 Wiederholungen/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Fertig' })).toHaveAttribute('href', '/');
  });
});
