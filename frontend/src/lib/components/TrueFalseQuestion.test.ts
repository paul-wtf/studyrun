import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import TrueFalseQuestion from './TrueFalseQuestion.svelte';
import { itemEntry } from './fixtures';
import { mockApi } from '#lib/test/mockApi.ts';

describe('TrueFalseQuestion', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('posts the boolean value', async () => {
    const { calls } = mockApi({
      'POST /api/runs/1/entries/0/answer': { correct: true, expected: 'Wahr', explanation: 'Stimmt.' }
    });
    render(TrueFalseQuestion, {
      props: { runId: 1, entry: itemEntry('true_false', { statement: 'Wasser ist nass.' }), onDone: vi.fn() }
    });
    await userEvent.click(screen.getByRole('button', { name: 'Wahr' }));
    expect(calls[0].body).toEqual({ answer: { value: true } });
    expect(await screen.findByText('Richtig')).toBeInTheDocument();
  });
});
