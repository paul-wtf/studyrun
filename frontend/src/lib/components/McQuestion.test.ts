import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import McQuestion from './McQuestion.svelte';
import { itemEntry } from './fixtures';
import { mockApi } from '#lib/test/mockApi.ts';

const entry = itemEntry('mc', { prompt: 'Welche Farbe?', options: ['Rot', 'Grün', 'Blau'] });

describe('McQuestion', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('posts the chosen index and shows feedback', async () => {
    const { calls } = mockApi({
      'POST /api/runs/1/entries/0/answer': { correct: false, expected: 'Blau', explanation: 'Der Himmel.' }
    });
    const onDone = vi.fn();
    render(McQuestion, { props: { runId: 1, entry, onDone } });
    await userEvent.click(screen.getByRole('button', { name: 'Grün' }));
    expect(calls[0].body).toEqual({ answer: { choice: 1 } });
    expect(await screen.findByText('Falsch')).toBeInTheDocument();
    expect(screen.getByText('Der Himmel.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Im Skript/ })).toHaveAttribute(
      'href',
      '/api/booklets/3/pdf#page=12'
    );
    await userEvent.click(screen.getByRole('button', { name: 'Weiter' }));
    expect(onDone).toHaveBeenCalled();
  });

  it('flags the item from the Melden menu', async () => {
    const { calls } = mockApi({
      'POST /api/runs/1/entries/0/answer': { correct: true, expected: 'Rot', explanation: 'x' },
      'POST /api/items/7/flag': { status: 'flagged' }
    });
    render(McQuestion, { props: { runId: 1, entry, onDone: vi.fn() } });
    await userEvent.click(screen.getByRole('button', { name: 'Rot' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Melden' }));
    await userEvent.click(screen.getByRole('button', { name: 'Nicht im Kurs' }));
    expect(calls.at(-1)).toMatchObject({ path: '/api/items/7/flag', body: { reason: 'not_in_course' } });
    expect(await screen.findByText('Gemeldet')).toBeInTheDocument();
  });
});
