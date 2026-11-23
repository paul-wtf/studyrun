import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import FlagEditor from './FlagEditor.svelte';
import { mockApi } from '#lib/test/mockApi.ts';

const MC = {
  id: 5, kind: 'mc' as const, source_page: 3, reason: 'wrong', chapter_title: 'Zelle', source: '/api/booklets/1/pdf#page=3',
  payload: { prompt: 'Was ist der Kern?', options: ['A', 'B', 'C'], answer_index: 1, explanation: 'Weil.' }
};

describe('FlagEditor', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('sends the edited payload', async () => {
    const onchanged = vi.fn();
    const { calls } = mockApi({ 'PUT /api/items/5': { status: 'active' } });
    render(FlagEditor, { item: MC, onchanged });
    const prompt = screen.getByLabelText('Frage');
    await userEvent.clear(prompt);
    await userEvent.type(prompt, 'Was ist der Zellkern?');
    await userEvent.clear(screen.getByLabelText('Antwortoptionen (eine pro Zeile)'));
    await userEvent.type(screen.getByLabelText('Antwortoptionen (eine pro Zeile)'), 'X{Enter}Y{Enter}Z');
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    await vi.waitFor(() => expect(onchanged).toHaveBeenCalled());
    expect(calls[0]).toEqual({
      method: 'PUT',
      path: '/api/items/5',
      body: {
        payload: {
          prompt: 'Was ist der Zellkern?',
          options: ['X', 'Y', 'Z'],
          answer_index: 1,
          explanation: 'Weil.'
        },
        source_page: 3
      }
    });
  });

  it('shows the German 422 message', async () => {
    mockApi({
      'PUT /api/items/5': () =>
        new Response(JSON.stringify({ detail: 'Ungültige Aufgabe: Quellseite' }), {
          status: 422,
          headers: { 'content-type': 'application/json' }
        })
    });
    render(FlagEditor, { item: MC, onchanged: vi.fn() });
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    expect(await screen.findByText('Ungültige Aufgabe: Quellseite')).toBeInTheDocument();
  });

  it('renders fields for the other kinds and sends a boolean for true_false', async () => {
    const { calls } = mockApi({ 'PUT /api/items/6': { status: 'active' } });
    render(FlagEditor, {
      item: { ...MC, id: 6, kind: 'true_false' as const, payload: { statement: 'S', correct: true, explanation: 'E' } },
      onchanged: vi.fn()
    });
    await userEvent.selectOptions(screen.getByLabelText('Richtige Antwort'), 'Falsch');
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    expect((calls[0].body as { payload: unknown }).payload).toEqual({
      statement: 'S', correct: false, explanation: 'E'
    });
  });

  it('deletes the item', async () => {
    const onchanged = vi.fn();
    const { calls } = mockApi({ 'DELETE /api/items/5': { status: 'deleted' } });
    render(FlagEditor, { item: MC, onchanged });
    await userEvent.click(screen.getByRole('button', { name: 'Löschen' }));
    await vi.waitFor(() => expect(onchanged).toHaveBeenCalled());
    expect(calls[0]).toMatchObject({ method: 'DELETE', path: '/api/items/5' });
  });
});
