import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import TrueFalseQuestion from './TrueFalseQuestion.svelte';
import { trueFalseEntry } from './fixtures';
import { mockApi } from '#lib/test/mockApi.ts';

describe('TrueFalseQuestion', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('posts the boolean value', async () => {
    const { calls } = mockApi({
      'POST /api/runs/1/entries/0/answer': { correct: true, expected: 'Wahr', explanation: 'Stimmt.' }
    });
    render(TrueFalseQuestion, {
      props: { runId: 1, entry: trueFalseEntry({ statement: 'Wasser ist nass.' }), onDone: vi.fn() }
    });
    await userEvent.click(screen.getByRole('button', { name: 'Wahr' }));
    expect(calls[0].body).toEqual({ answer: { value: true } });
    expect(await screen.findByText('Richtig')).toBeInTheDocument();
  });

  it('marks the right value and a wrong pick from the result, not from its text', async () => {
    mockApi({
      'POST /api/runs/1/entries/0/answer': { correct: false, expected: 'nein', explanation: '' }
    });
    render(TrueFalseQuestion, {
      props: { runId: 1, entry: trueFalseEntry({ statement: 'Eis ist warm.' }), onDone: vi.fn() }
    });
    await userEvent.click(screen.getByRole('button', { name: 'Wahr' }));
    await screen.findByText('Falsch', { selector: 'h2' });
    expect(screen.getByRole('button', { name: 'Wahr' })).toHaveClass('wrong');
    expect(screen.getByRole('button', { name: 'Wahr' })).not.toHaveClass('correct');
    expect(screen.getByRole('button', { name: 'Falsch' })).toHaveClass('correct');
  });
});
