import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import Page from './+page.svelte';
import { mockApi } from '#lib/test/mockApi.ts';

const FLAG = {
  id: 5, kind: 'true_false', source_page: 3, reason: 'not_in_course', chapter_title: 'Zelle',
  source: '/api/booklets/1/pdf#page=3', payload: { statement: 'S', correct: true, explanation: 'E' }
};

describe('flags page', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('lists flagged items with the reason and removes one after deleting', async () => {
    let flags = [FLAG];
    mockApi({
      'GET /api/flags': () => flags,
      'DELETE /api/items/5': () => {
        flags = [];
        return { status: 'deleted' };
      }
    });
    render(Page);
    expect(await screen.findByText('Nicht im Kurs')).toBeInTheDocument();
    expect(screen.getByText(/Zelle/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Im Skript/ })).toHaveAttribute('href', FLAG.source);
    await userEvent.click(screen.getByRole('button', { name: 'Löschen' }));
    expect(await screen.findByText('Keine gemeldeten Fragen.')).toBeInTheDocument();
  });
});
