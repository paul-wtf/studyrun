import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import { mockApi } from '#lib/test/mockApi.ts';
import { T0, at, exam, finishedExam } from '#lib/test/mockFixtures.ts';

vi.mock('$app/state', () => ({ page: { params: { id: '7' } } }));

import Page from './+page.svelte';

const later = (minutes: number) => new Date(Date.now() + minutes * 60_000).toISOString();
const failure = (status: number, detail = 'Fehler') =>
  new Response(JSON.stringify({ detail }), { status, headers: { 'content-type': 'application/json' } });
const posts = (calls: { method: string; path: string }[], path: string) =>
  calls.filter((c) => c.method === 'POST' && c.path === path);

describe('mock exam page', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('resumes with the time left until the server deadline and the saved answers', async () => {
    vi.useFakeTimers({ now: new Date(T0.getTime() + 43 * 60_000), shouldAdvanceTime: true });
    const resumed = exam({ deadline: at(90) });
    resumed.entries[0] = { ...resumed.entries[0], answered: true, answer: { choice: 1 } };
    mockApi({ 'GET /api/mock/7': resumed });
    render(Page);
    expect(await screen.findByRole('timer')).toHaveTextContent('47:00');
    expect(screen.getByRole('button', { name: 'Planung' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Frage 1, beantwortet' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Frage 2, offen' })).toBeInTheDocument();
  });

  it('saves a choice at once and shows no feedback before the end', async () => {
    const { calls } = mockApi({
      'GET /api/mock/7': exam({ deadline: later(90) }),
      'POST /api/mock/7/answers/0': { n: 0, answered: true }
    });
    render(Page);
    await userEvent.click(await screen.findByRole('button', { name: 'Werkstoffe' }));
    await vi.waitFor(() => expect(posts(calls, '/api/mock/7/answers/0')).toHaveLength(1));
    expect(posts(calls, '/api/mock/7/answers/0')[0]).toMatchObject({ body: { answer: { choice: 0 } } });
    expect(screen.getByRole('button', { name: 'Werkstoffe' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByText(/Richtig|Falsch|Richtige Antwort|Im Heft nachlesen/)).not.toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Frage 1, beantwortet' })).toBeInTheDocument();
  });

  it('saves typed text once the typing pauses', async () => {
    const { calls } = mockApi({
      'GET /api/mock/7': exam({ deadline: later(90) }),
      'POST /api/mock/7/answers/3': { n: 3, answered: true }
    });
    render(Page);
    await userEvent.click(await screen.findByRole('button', { name: 'Frage 4, offen' }));
    await userEvent.type(screen.getByRole('textbox', { name: 'Antwort' }), 'Ergebnis durch Aufwand');
    expect(posts(calls, '/api/mock/7/answers/3')).toHaveLength(0);
    await vi.waitFor(() => expect(posts(calls, '/api/mock/7/answers/3')).toHaveLength(1));
    expect(posts(calls, '/api/mock/7/answers/3')[0]).toMatchObject({ body: { answer: { text: 'Ergebnis durch Aufwand' } } });
  });

  it('moves between items with Weiter and Zurück', async () => {
    mockApi({ 'GET /api/mock/7': exam({ deadline: later(90) }) });
    render(Page);
    await userEvent.click(await screen.findByRole('button', { name: 'Weiter' }));
    expect(screen.getByText('Wasser ist nass.')).toBeInTheDocument();
    expect(screen.getByText('Frage 2 von 4')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Zurück' }));
    expect(screen.getByText('Welcher Faktor ist dispositiv?')).toBeInTheDocument();
  });

  it('calls finish exactly once when the timer reaches zero', async () => {
    vi.useFakeTimers({ now: T0, shouldAdvanceTime: true });
    let release = () => {};
    const { calls } = mockApi({
      'GET /api/mock/7': exam({ deadline: new Date(T0.getTime() + 2_000).toISOString() }),
      'POST /api/mock/7/finish': () => new Promise((ok) => (release = () => ok(finishedExam())))
    });
    render(Page);
    expect(await screen.findByRole('timer')).toHaveTextContent('00:02');
    await vi.advanceTimersByTimeAsync(5_000);
    expect(await screen.findByText('Wird ausgewertet …')).toBeInTheDocument();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(posts(calls, '/api/mock/7/finish')).toHaveLength(1);
    release();
    expect(await screen.findByText('25 %')).toBeInTheDocument();
    expect(posts(calls, '/api/mock/7/finish')).toHaveLength(1);
  });

  it('calls finish once when a save hits the deadline as the timer runs out', async () => {
    vi.useFakeTimers({ now: T0, shouldAdvanceTime: true });
    const { calls } = mockApi({
      'GET /api/mock/7': exam({ deadline: new Date(T0.getTime() + 2_000).toISOString() }),
      'POST /api/mock/7/answers/0': () => new Promise((ok) => setTimeout(() => ok(failure(409, 'Zeit abgelaufen')), 2_500)),
      'POST /api/mock/7/finish': finishedExam()
    });
    render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: 'Planung' }));
    await vi.advanceTimersByTimeAsync(5_000);
    expect(await screen.findByText('Nicht bestanden')).toBeInTheDocument();
    expect(posts(calls, '/api/mock/7/finish')).toHaveLength(1);
  });

  it('finishes an exam whose time ran out while the page was closed', async () => {
    const { calls } = mockApi({
      'GET /api/mock/7': exam({ deadline: later(-5), expired: true }),
      'POST /api/mock/7/finish': finishedExam()
    });
    render(Page);
    expect(await screen.findByText('25 %')).toBeInTheDocument();
    expect(posts(calls, '/api/mock/7/finish')).toHaveLength(1);
  });

  it('asks before submitting and names the unanswered items', async () => {
    const { calls } = mockApi({
      'GET /api/mock/7': exam({ deadline: later(90) }),
      'POST /api/mock/7/finish': finishedExam()
    });
    render(Page);
    await userEvent.click(await screen.findByRole('button', { name: 'Abgeben' }));
    const dialog = screen.getByRole('group', { name: 'Abgeben?' });
    expect(within(dialog).getByText(/4 von 4 Fragen sind noch unbeantwortet/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Weiter bearbeiten' }));
    expect(screen.queryByRole('group', { name: 'Abgeben?' })).not.toBeInTheDocument();
    expect(posts(calls, '/api/mock/7/finish')).toHaveLength(0);
    await userEvent.click(screen.getByRole('button', { name: 'Abgeben' }));
    await userEvent.click(screen.getByRole('button', { name: 'Jetzt abgeben' }));
    expect(await screen.findByText('25 %')).toBeInTheDocument();
    expect(posts(calls, '/api/mock/7/finish')).toHaveLength(1);
  });

  it('saves pending text before submitting', async () => {
    const { calls } = mockApi({
      'GET /api/mock/7': exam({ deadline: later(90) }),
      'POST /api/mock/7/answers/3': { n: 3, answered: true },
      'POST /api/mock/7/finish': finishedExam()
    });
    render(Page);
    await userEvent.click(await screen.findByRole('button', { name: 'Frage 4, offen' }));
    await userEvent.type(screen.getByRole('textbox', { name: 'Antwort' }), 'Kurz');
    await userEvent.click(screen.getByRole('button', { name: 'Abgeben' }));
    expect(screen.getByText(/3 von 4 Fragen sind noch unbeantwortet/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Jetzt abgeben' }));
    await screen.findByText('25 %');
    const paths = calls.filter((c) => c.method === 'POST').map((c) => c.path);
    expect(paths).toEqual(['/api/mock/7/answers/3', '/api/mock/7/finish']);
  });

  it('re-fetches the exam instead of failing when finish errors', async () => {
    const { calls } = mockApi({
      'GET /api/mock/7': exam({ deadline: later(-1), expired: true }),
      'POST /api/mock/7/finish': failure(504, 'Gateway Timeout')
    });
    render(Page);
    expect(await screen.findByRole('button', { name: 'Auswertung fortsetzen' })).toBeInTheDocument();
    expect(calls.filter((c) => c.method === 'GET')).toHaveLength(2);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByText('Gateway Timeout')).not.toBeInTheDocument();
  });

  it('shows the result the re-fetch finds after a finish error', async () => {
    let gets = 0;
    mockApi({
      'GET /api/mock/7': () => (gets++ === 0 ? exam({ deadline: later(-1), expired: true }) : finishedExam()),
      'POST /api/mock/7/finish': failure(502)
    });
    render(Page);
    expect(await screen.findByText('25 %')).toBeInTheDocument();
  });

  it('submits when the server says the time is up on a save', async () => {
    const { calls } = mockApi({
      'GET /api/mock/7': exam({ deadline: later(90) }),
      'POST /api/mock/7/answers/0': failure(409, 'Zeit abgelaufen'),
      'POST /api/mock/7/finish': finishedExam()
    });
    render(Page);
    await userEvent.click(await screen.findByRole('button', { name: 'Planung' }));
    expect(await screen.findByText('25 %')).toBeInTheDocument();
    expect(posts(calls, '/api/mock/7/finish')).toHaveLength(1);
  });

  it('shows an already finished exam as its result', async () => {
    const { calls } = mockApi({ 'GET /api/mock/7': finishedExam() });
    render(Page);
    expect(await screen.findByText('25 %')).toBeInTheDocument();
    expect(posts(calls, '/api/mock/7/finish')).toHaveLength(0);
    expect(screen.queryByRole('timer')).not.toBeInTheDocument();
  });

  it('updates the score after a self-rating', async () => {
    const rated = finishedExam();
    rated.entries[3] = { ...rated.entries[3], review: { ...rated.entries[3].review!, score: 100, correct: true } };
    rated.result = { ...rated.result!, score: 50, passed: true, pending_self_rating: 0 };
    const { calls } = mockApi({ 'GET /api/mock/7': finishedExam(), 'POST /api/mock/7/self-rate/3': rated });
    render(Page);
    expect(await screen.findByText('Nicht bestanden')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Wusste ich' }));
    await vi.waitFor(() => expect(screen.getByRole('region', { name: 'Ergebnis' })).toHaveTextContent(/Rechnungswesen 50 % Bestanden bestanden ab 50 %/));
    expect(posts(calls, '/api/mock/7/self-rate/3')[0]).toMatchObject({ body: { rating: 'good' } });
    expect(screen.queryByRole('button', { name: 'Wusste ich' })).not.toBeInTheDocument();
  });
});
