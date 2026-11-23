import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import FreeQuestion from './FreeQuestion.svelte';
import { itemEntry } from './fixtures';
import { mockApi } from '#lib/test/mockApi.ts';

const entry = itemEntry('free', { prompt: 'Erkläre die Zelle.' });

describe('FreeQuestion', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('shows score, feedback and missing points', async () => {
    mockApi({
      'POST /api/runs/1/entries/0/answer': {
        score: 60,
        feedback: 'Solide Grundlage.',
        missing: ['Zellkern'],
        model_answer: 'Die Zelle hat einen Kern.'
      }
    });
    render(FreeQuestion, { props: { runId: 1, entry, onDone: vi.fn() } });
    await userEvent.type(screen.getByRole('textbox'), 'Eine Zelle');
    await userEvent.click(screen.getByRole('button', { name: 'Antworten' }));
    expect(await screen.findByText('60 von 100')).toBeInTheDocument();
    expect(screen.getByText('Solide Grundlage.')).toBeInTheDocument();
    expect(screen.getByText('Zellkern')).toBeInTheDocument();
  });

  it('offers self-rating when grading is unavailable', async () => {
    const { calls } = mockApi({
      'POST /api/runs/1/entries/0/answer': {
        grading_unavailable: true,
        reason: 'Tagesbudget erreicht',
        model_answer: 'Die Zelle hat einen Kern.'
      },
      'POST /api/runs/1/entries/0/self-rate': { done: true }
    });
    const onDone = vi.fn();
    render(FreeQuestion, { props: { runId: 1, entry, onDone } });
    await userEvent.type(screen.getByRole('textbox'), 'Eine Zelle');
    await userEvent.click(screen.getByRole('button', { name: 'Antworten' }));
    expect(await screen.findByText('Die Zelle hat einen Kern.')).toBeInTheDocument();
    expect(screen.getByText('Tagesbudget erreicht')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Wusste ich nicht' }));
    expect(calls.at(-1)).toMatchObject({
      path: '/api/runs/1/entries/0/self-rate',
      body: { rating: 'again' }
    });
    expect(onDone).toHaveBeenCalled();
  });
});
