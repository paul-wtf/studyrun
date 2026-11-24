import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/svelte';
import MockResult from './MockResult.svelte';
import { finishedExam } from '#lib/test/mockFixtures.ts';

describe('MockResult', () => {
  it('shows the total against the pass mark and the chapters weakest first', () => {
    render(MockResult, { props: { exam: finishedExam(), onrate: vi.fn() } });
    expect(screen.getByText('25 %')).toBeInTheDocument();
    expect(screen.getByText('Nicht bestanden')).toBeInTheDocument();
    expect(screen.getByText(/bestanden ab 50 %/)).toBeInTheDocument();
    const rows = within(screen.getByRole('list', { name: 'Kapitel' })).getAllByRole('listitem');
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringMatching(/Prinzipien.*0 %/),
      expect.stringMatching(/Grundbegriffe.*50 %/)
    ]);
  });

  it('shows each answer next to the right one, with explanation and source', () => {
    render(MockResult, { props: { exam: finishedExam(), onrate: vi.fn() } });
    const first = screen.getByRole('article', { name: 'Frage 1' });
    expect(within(first).getByText('Werkstoffe')).toBeInTheDocument();
    expect(within(first).getByText('Planung')).toBeInTheDocument();
    expect(within(first).getByText('Planung ist ein dispositiver Faktor.')).toBeInTheDocument();
    expect(within(first).getByRole('link', { name: 'Im Heft nachlesen' })).toHaveAttribute('href', '/api/booklets/1/pdf#page=3');
    const third = screen.getByRole('article', { name: 'Frage 3' });
    expect(within(third).getByText('Nicht beantwortet')).toBeInTheDocument();
  });

  it('offers a self-rating only for ungraded free answers', () => {
    const onrate = vi.fn();
    render(MockResult, { props: { exam: finishedExam(), onrate } });
    expect(screen.getAllByRole('button', { name: 'Wusste ich' })).toHaveLength(1);
    const free = screen.getByRole('article', { name: 'Frage 4' });
    expect(within(free).getByText('Effizienz ist das Verhältnis von Ergebnis zu Aufwand.')).toBeInTheDocument();
    expect(screen.getByText(/1 freie Antwort wartet auf deine Selbstbewertung/)).toBeInTheDocument();
  });
});
