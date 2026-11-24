import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import FreeQuestion from './FreeQuestion.svelte';
import { freeEntry } from './fixtures';
import { mockApi } from '#lib/test/mockApi.ts';

const entry = freeEntry({ prompt: 'Erkläre die Zelle.' });

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

  it('goes straight to self-rating when grading already failed for this entry', async () => {
    const { calls } = mockApi({ 'POST /api/runs/1/entries/0/self-rate': { done: true } });
    const onDone = vi.fn();
    const failed = { ...entry, grading_unavailable: true, model_answer: 'Die Zelle hat einen Kern.' };
    render(FreeQuestion, { props: { runId: 1, entry: failed, onDone } });
    expect(screen.getByText('Die Zelle hat einen Kern.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Antworten' })).not.toBeInTheDocument();
    expect(screen.getByRole('textbox')).toBeDisabled();
    await userEvent.keyboard('{Control>}{Enter}{/Control}');
    await userEvent.click(screen.getByRole('button', { name: 'Wusste ich' }));
    expect(calls).toEqual([
      { method: 'POST', path: '/api/runs/1/entries/0/self-rate', body: { rating: 'good' } }
    ]);
    expect(onDone).toHaveBeenCalled();
  });

  it('sends a self-rating only once while it is on its way', async () => {
    let release: (r: Response) => void = () => {};
    const fetchMock = vi.fn(
      () => new Promise<Response>((resolve) => (release = resolve))
    );
    vi.stubGlobal('fetch', fetchMock);
    const failed = { ...entry, grading_unavailable: true, model_answer: 'Muster' };
    render(FreeQuestion, { props: { runId: 1, entry: failed, onDone: vi.fn() } });
    await userEvent.click(screen.getByRole('button', { name: 'Wusste ich' }));
    await userEvent.click(screen.getByRole('button', { name: 'Wusste ich nicht' }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    release(new Response('{"done":true}', { headers: { 'content-type': 'application/json' } }));
  });
});
