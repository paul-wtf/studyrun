import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/svelte';
import ConflictList from './ConflictList.svelte';
import { CONFLICTS } from '#lib/test/planFixtures.ts';

describe('ConflictList', () => {
  it('shows every conflict kind with its subject and message', () => {
    render(ConflictList, { conflicts: CONFLICTS });
    const items = within(screen.getByRole('region', { name: 'Konflikte' })).getAllByRole('listitem');
    expect(items).toHaveLength(7);
    for (const c of CONFLICTS) expect(screen.getByText(c.message)).toBeInTheDocument();
    expect(within(items[5]).getByText('Personal')).toBeInTheDocument();
  });

  it('renders nothing without conflicts', () => {
    render(ConflictList, { conflicts: [] });
    expect(screen.queryByRole('region', { name: 'Konflikte' })).not.toBeInTheDocument();
  });
});
