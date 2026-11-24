import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import ClozeQuestion from './ClozeQuestion.svelte';
import { clozeEntry } from './fixtures';
import { mockApi } from '#lib/test/mockApi.ts';

describe('ClozeQuestion', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('submits on Enter', async () => {
    const { calls } = mockApi({
      'POST /api/runs/1/entries/0/answer': { correct: true, expected: 'Mitochondrium', explanation: 'Kraftwerk.' }
    });
    render(ClozeQuestion, {
      props: { runId: 1, entry: clozeEntry({ text: 'Das ___ ist das Kraftwerk.' }), onDone: vi.fn() }
    });
    await userEvent.type(screen.getByRole('textbox'), 'Mitochondrium{Enter}');
    expect(calls[0].body).toEqual({ answer: { text: 'Mitochondrium' } });
    expect(await screen.findByText('Richtig')).toBeInTheDocument();
  });
});
