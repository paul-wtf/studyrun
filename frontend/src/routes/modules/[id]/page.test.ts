import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { mockApi } from '#lib/test/mockApi.ts';

vi.mock('$app/state', () => ({ page: { params: { id: '4' } } }));

import Page from './+page.svelte';

describe('module page', () => {
  afterEach(() => vi.unstubAllGlobals());

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
