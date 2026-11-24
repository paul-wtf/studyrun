import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import PlanEntryCard from './PlanEntryCard.svelte';
import { mockApi } from '#lib/test/mockApi.ts';
import { planEntry, subject, TODAY } from '#lib/test/planFixtures.ts';

const proposed = planEntry({ state: 'open', sitting: '2027-01-31', register_by: '2027-01-10', study_from: TODAY, study_until: '2027-01-20' });

function show(entry = proposed, s = subject()) {
  const onchange = vi.fn();
  render(PlanEntryCard, { entry, subject: s, today: TODAY, onchange });
  return onchange;
}

describe('PlanEntryCard', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('shows the proposal with its registration deadline', () => {
    show();
    expect(screen.getByText('Vorschlag')).toBeInTheDocument();
    expect(screen.getByText('31.01.2027')).toBeInTheDocument();
    expect(screen.getByText('Anmelden bis 10.01.2027')).toBeInTheDocument();
  });

  it('hides the deadline once it has passed', () => {
    show(planEntry({ state: 'planned', sitting: '2026-12-06', register_by: '2026-11-15' }));
    expect(screen.queryByText(/Anmelden bis/)).not.toBeInTheDocument();
  });

  it('registers for the proposed sitting', async () => {
    const { calls } = mockApi({ 'POST /api/subjects/1/attempts': { id: 9, sitting: '2027-01-31', status: 'registered' } });
    const onchange = show();
    await userEvent.click(screen.getByRole('button', { name: 'Angemeldet' }));
    await vi.waitFor(() => expect(onchange).toHaveBeenCalled());
    expect(calls[0]).toMatchObject({ method: 'POST', path: '/api/subjects/1/attempts', body: { sitting: '2027-01-31', status: 'registered' } });
  });

  it('plans another sitting and refuses one whose registration closed', async () => {
    const { calls } = mockApi({ 'POST /api/subjects/1/attempts': { id: 9, sitting: '2027-03-14', status: 'planned' } });
    const onchange = show();
    await userEvent.click(screen.getByRole('button', { name: 'Anderen Termin wählen' }));
    const select = screen.getByLabelText('Termin');
    expect(screen.queryByRole('option', { name: /08\.11\.2026/ })).not.toBeInTheDocument();
    await userEvent.selectOptions(select, '2026-12-06');
    expect(screen.getByRole('option', { name: '06.12.2026 (Anmeldung vorbei)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Termin übernehmen' })).toBeDisabled();
    await userEvent.selectOptions(select, '2027-03-14');
    await userEvent.click(screen.getByRole('button', { name: 'Termin übernehmen' }));
    await vi.waitFor(() => expect(onchange).toHaveBeenCalled());
    expect(calls[0].body).toEqual({ sitting: '2027-03-14', status: 'planned' });
  });

  it('records a registration made for a sitting of its own choice', async () => {
    const { calls } = mockApi({ 'POST /api/subjects/1/attempts': { id: 9, sitting: '2026-12-06', status: 'registered' } });
    show();
    await userEvent.click(screen.getByRole('button', { name: 'Anderen Termin wählen' }));
    await userEvent.selectOptions(screen.getByLabelText('Termin'), '2026-12-06');
    await userEvent.click(screen.getByRole('button', { name: 'Dort angemeldet' }));
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ sitting: '2026-12-06', status: 'registered' });
  });

  it('drops a sitting planned by hand', async () => {
    const s = subject({ attempts: [{ id: 4, sitting: '2027-03-14', status: 'planned' }] });
    const { calls } = mockApi({ 'DELETE /api/attempts/4': new Response(null, { status: 204 }) });
    const onchange = show(planEntry({ state: 'planned', sitting: '2027-03-14', register_by: '2027-02-21' }), s);
    await userEvent.click(screen.getByRole('button', { name: 'Eigenen Termin verwerfen' }));
    await vi.waitFor(() => expect(onchange).toHaveBeenCalled());
    expect(calls[0]).toMatchObject({ method: 'DELETE', path: '/api/attempts/4' });
  });

  it.each([
    ['Bestanden', 'passed'],
    ['Nicht bestanden', 'failed']
  ])('records %s on the exam day', async (name, status) => {
    const s = subject({ attempts: [{ id: 5, sitting: TODAY, status: 'registered' }] });
    const { calls } = mockApi({ 'PATCH /api/attempts/5': { id: 5, sitting: TODAY, status } });
    const onchange = show(planEntry({ state: 'registered', sitting: TODAY }), s);
    expect(screen.queryByRole('button', { name: 'Anderen Termin wählen' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name }));
    await vi.waitFor(() => expect(onchange).toHaveBeenCalled());
    expect(calls[0]).toMatchObject({ method: 'PATCH', path: '/api/attempts/5', body: { status } });
  });

  it('asks for the result of a past exam', async () => {
    const s = subject({ attempts: [{ id: 6, sitting: '2026-11-08', status: 'registered' }] });
    const { calls } = mockApi({ 'PATCH /api/attempts/6': { id: 6, sitting: '2026-11-08', status: 'failed' } });
    show(planEntry({ state: 'needs_result', sitting: '2026-11-08' }), s);
    expect(screen.queryByRole('button', { name: 'Bestanden' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Ergebnis eintragen' }));
    await userEvent.click(screen.getByRole('button', { name: 'Nicht bestanden' }));
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ status: 'failed' });
  });

  it('offers no result before the exam day', () => {
    show(planEntry({ state: 'registered', sitting: '2026-12-06' }), subject({ attempts: [{ id: 5, sitting: '2026-12-06', status: 'registered' }] }));
    expect(screen.queryByRole('button', { name: 'Bestanden' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Anderen Termin wählen' })).toBeInTheDocument();
  });

  it('shows the server message when a change is refused', async () => {
    mockApi({
      'POST /api/subjects/1/attempts': new Response(JSON.stringify({ detail: 'Der Termin liegt in der Vergangenheit' }), {
        status: 422,
        headers: { 'content-type': 'application/json' }
      })
    });
    show();
    await userEvent.click(screen.getByRole('button', { name: 'Angemeldet' }));
    expect(await screen.findByText('Der Termin liegt in der Vergangenheit')).toBeInTheDocument();
  });

  it.each([
    ['no_material', 'Module zuordnen', '/modules'],
    ['not_plannable', 'Semesterstart eintragen', '/subjects#semester']
  ] as const)('points %s to the fix', (state, name, href) => {
    show(planEntry({ state }));
    expect(screen.getByRole('link', { name })).toHaveAttribute('href', href);
    expect(screen.queryByRole('button', { name: 'Angemeldet' })).not.toBeInTheDocument();
  });

  it('marks a sitting that the current pace does not reach', () => {
    show({ ...proposed, feasible: false });
    expect(screen.getByText(/Beim aktuellen Tempo wird es knapp/)).toBeInTheDocument();
  });
});
