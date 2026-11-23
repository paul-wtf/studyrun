import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import ChapterList from './ChapterList.svelte';
import { mockApi } from '#lib/test/mockApi.ts';

const ch = (over: object) => ({
  id: 1, booklet_id: 1, index: 0, title: 'Zelle', first_page: 1, last_page: 4,
  status: 'ready', error: null, waiting_reason: null, active_items: 6, ...over
});

describe('ChapterList', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('polls every 30 s while generating and stops once everything is ready', async () => {
    let n = 0;
    const { calls } = mockApi({
      'GET /api/modules/2/chapters': () => [ch({ status: n++ < 2 ? 'generating' : 'ready' })]
    });
    const { unmount } = render(ChapterList, { moduleId: 2 });
    expect(await screen.findByText('Wird erzeugt')).toBeInTheDocument();
    expect(screen.getByText(/bis zu einer Stunde/)).toBeInTheDocument();
    await vi.advanceTimersByTimeAsync(29_000);
    expect(calls).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1_500);
    expect(calls).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(await screen.findByText('Fertig')).toBeInTheDocument();
    expect(calls).toHaveLength(3);
    await vi.advanceTimersByTimeAsync(120_000);
    expect(calls).toHaveLength(3);
    unmount();
  });

  it('does not poll when all chapters are ready or failed', async () => {
    const { calls } = mockApi({
      'GET /api/modules/2/chapters': [ch({}), ch({ id: 2, status: 'failed', error: 'kaputt' })]
    });
    render(ChapterList, { moduleId: 2 });
    await screen.findByText('kaputt');
    await vi.advanceTimersByTimeAsync(120_000);
    expect(calls).toHaveLength(1);
    expect(screen.queryByText(/bis zu einer Stunde/)).not.toBeInTheDocument();
  });

  it('stops polling on unmount', async () => {
    const { calls } = mockApi({ 'GET /api/modules/2/chapters': [ch({ status: 'pending' })] });
    const { unmount } = render(ChapterList, { moduleId: 2 });
    await screen.findByText('Wartet');
    unmount();
    await vi.advanceTimersByTimeAsync(120_000);
    expect(calls).toHaveLength(1);
  });

  it('shows the waiting reason and retries a failed chapter', async () => {
    let failed = true;
    const { calls } = mockApi({
      'GET /api/modules/2/chapters': () => [
        ch({ id: 7, status: failed ? 'failed' : 'pending', error: failed ? 'Zeitüberschreitung' : null }),
        ch({ id: 8, status: 'pending', waiting_reason: 'Tagesbudget erreicht' })
      ],
      'POST /api/chapters/7/retry': () => {
        failed = false;
        return ch({ id: 7, status: 'pending' });
      }
    });
    render(ChapterList, { moduleId: 2 });
    expect(await screen.findByText('Tagesbudget erreicht')).toBeInTheDocument();
    expect(screen.getByText('Zeitüberschreitung')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Neu versuchen' }));
    await vi.waitFor(() => expect(screen.queryByText('Zeitüberschreitung')).not.toBeInTheDocument());
    expect(calls.some((c) => c.path === '/api/chapters/7/retry' && c.method === 'POST')).toBe(true);
  });
});
