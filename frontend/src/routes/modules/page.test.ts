import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import Page from './+page.svelte';
import { mockApi } from '#lib/test/mockApi.ts';

const mod = (id: number, name: string, position: number, subject_id: number | null = null) => ({ id, name, position, subject_id, booklets: [] });
const SUBJECTS = [
  { id: 1, name: 'Rechnungswesen' },
  { id: 2, name: 'Statistik' }
];

describe('modules page', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('creates a module and reorders with the arrows', async () => {
    let list = [mod(1, 'Bio', 0), mod(2, 'Chemie', 1)];
    const { calls } = mockApi({
      'GET /api/modules': () => list,
      'GET /api/subjects': [],
      'POST /api/modules': () => {
        list = [...list, mod(3, 'Physik', 2)];
        return list[2];
      },
      'PATCH /api/modules/2': () => {
        list = [list[1], list[0], ...list.slice(2)];
        return list[0];
      }
    });
    render(Page);
    expect(await screen.findByRole('link', { name: 'Bio' })).toHaveAttribute('href', '/modules/1');
    await userEvent.type(screen.getByLabelText('Neues Modul'), 'Physik');
    await userEvent.click(screen.getByRole('button', { name: 'Anlegen' }));
    expect(await screen.findByRole('link', { name: 'Physik' })).toBeInTheDocument();
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ name: 'Physik' });
    await userEvent.click(screen.getByRole('button', { name: 'Chemie nach oben' }));
    await vi.waitFor(() =>
      expect(screen.getAllByRole('link').map((l) => l.textContent)).toEqual(['Chemie', 'Bio', 'Physik'])
    );
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ position: 0 });
  });

  it('assigns a module to a subject and takes it off again', async () => {
    let list = [mod(1, 'Bio', 0)];
    const { calls } = mockApi({
      'GET /api/modules': () => list,
      'GET /api/subjects': SUBJECTS,
      'PATCH /api/modules/1': (body: unknown) => {
        list = [mod(1, 'Bio', 0, (body as { subject_id: number | null }).subject_id)];
        return list[0];
      }
    });
    render(Page);
    const select = await screen.findByLabelText('Fach für Bio');
    expect(select).toHaveValue('');
    await userEvent.selectOptions(select, 'Statistik');
    await vi.waitFor(() => expect(calls.filter((c) => c.method === 'PATCH')).toHaveLength(1));
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ subject_id: 2 });
    await vi.waitFor(() => expect(screen.getByLabelText('Fach für Bio')).toHaveValue('2'));
    await userEvent.selectOptions(screen.getByLabelText('Fach für Bio'), 'Kein Fach');
    await vi.waitFor(() => expect(calls.filter((c) => c.method === 'PATCH')).toHaveLength(2));
    expect(calls.filter((c) => c.method === 'PATCH')[1].body).toEqual({ subject_id: null });
  });
});
