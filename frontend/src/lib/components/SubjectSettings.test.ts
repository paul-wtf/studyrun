import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import SubjectSettings from './SubjectSettings.svelte';
import { mockApi } from '#lib/test/mockApi.ts';
import { subject } from '#lib/test/planFixtures.ts';

describe('SubjectSettings', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('saves the not-before date and the pass mark', async () => {
    const onchange = vi.fn();
    const { calls } = mockApi({ 'PATCH /api/subjects/1': subject() });
    render(SubjectSettings, { subject: subject(), onchange });
    await fireEvent.input(screen.getByLabelText('Nicht vor'), { target: { value: '2027-02-01' } });
    await userEvent.clear(screen.getByLabelText('Bestehensgrenze Bosskampf (%)'));
    await userEvent.type(screen.getByLabelText('Bestehensgrenze Bosskampf (%)'), '60');
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    await vi.waitFor(() => expect(onchange).toHaveBeenCalled());
    expect(calls[0]).toMatchObject({ method: 'PATCH', path: '/api/subjects/1', body: { not_before: '2027-02-01', pass_mark: 60 } });
  });

  it('clears the not-before date', async () => {
    const { calls } = mockApi({ 'PATCH /api/subjects/1': subject() });
    render(SubjectSettings, { subject: subject({ not_before: '2027-02-01' }), onchange: vi.fn() });
    await fireEvent.input(screen.getByLabelText('Nicht vor'), { target: { value: '' } });
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ not_before: null, pass_mark: 50 });
  });
});
