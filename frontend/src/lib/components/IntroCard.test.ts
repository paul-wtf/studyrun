import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import IntroCard from './IntroCard.svelte';
import { mockApi } from '#lib/test/mockApi.ts';

const entry = {
  n: 2,
  type: 'intro' as const,
  done: false,
  grading_unavailable: false,
  chapter: {
    id: 5,
    title: 'Die Zelle',
    summary: 'Bausteine des Lebens.',
    concepts: ['Zellkern', 'Membran'],
    source: '/api/booklets/3/pdf#page=4'
  }
};

describe('IntroCard', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('shows summary and concepts and acks on Weiter', async () => {
    const { calls } = mockApi({ 'POST /api/runs/1/entries/2/ack': { done: true } });
    const onDone = vi.fn();
    render(IntroCard, { props: { runId: 1, entry, onDone } });
    expect(screen.getByText('Bausteine des Lebens.')).toBeInTheDocument();
    expect(screen.getByText('Zellkern')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Weiter' }));
    expect(calls).toEqual([{ method: 'POST', path: '/api/runs/1/entries/2/ack', body: undefined }]);
    expect(onDone).toHaveBeenCalled();
  });
});
