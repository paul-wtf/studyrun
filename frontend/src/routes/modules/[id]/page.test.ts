import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { mockApi } from '#lib/test/mockApi.ts';

vi.mock('$app/state', () => ({ page: { params: { id: '4' } } }));

import Page from './+page.svelte';

describe('module page', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('refreshes the booklet status when the polled chapters change', async () => {
    let done = false;
    const counts = (ready: number, generating: number) => ({ pending: 0, generating, verifying: 0, ready, failed: 0 });
    mockApi({
      'GET /api/modules': () => [
        { id: 4, name: 'Bio', position: 0, booklets: [{ id: 9, filename: 'heft.pdf', page_count: 4,
          status: done ? 'ready' : 'processing', chapters: done ? counts(1, 0) : counts(0, 1) }] }
      ],
      'GET /api/modules/4/chapters': () => [{ id: 1, booklet_id: 9, index: 0, title: 'Zelle', first_page: 1,
        last_page: 4, status: done ? 'ready' : 'generating', error: null, waiting_reason: null, active_items: 3 }]
    });
    render(Page);
    expect(await screen.findByText(/In Arbeit/)).toBeInTheDocument();
    done = true;
    await vi.advanceTimersByTimeAsync(30_500);
    expect(await screen.findByText(/4 Seiten · Fertig/)).toBeInTheDocument();
  });

  it('shows booklets, upload and chapters', async () => {
    mockApi({
      'GET /api/modules': [
        {
          id: 4, name: 'Bio', position: 0,
          booklets: [{ id: 9, filename: 'heft.pdf', page_count: 40, status: 'processing',
            chapters: { pending: 1, generating: 0, verifying: 0, ready: 2, failed: 0 } }]
        }
      ],
      'GET /api/modules/4/chapters': []
    });
    render(Page);
    expect(await screen.findByRole('heading', { name: 'Bio' })).toBeInTheDocument();
    expect(screen.getByText(/heft\.pdf/)).toBeInTheDocument();
    expect(screen.getByText(/40 Seiten/)).toBeInTheDocument();
    expect(screen.getByText(/In Arbeit/)).toBeInTheDocument();
    expect(screen.getByLabelText('PDF-Datei')).toBeInTheDocument();
  });
});
