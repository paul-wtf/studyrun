import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import UploadBooklet from './UploadBooklet.svelte';
import { mockApi } from '#lib/test/mockApi.ts';

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

const pdf = () => new File(['%PDF'], 'heft.pdf', { type: 'application/pdf' });

async function pick() {
  await userEvent.upload(screen.getByLabelText('PDF-Datei'), pdf());
  await userEvent.click(screen.getByRole('button', { name: 'Hochladen' }));
}

describe('UploadBooklet', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('asks for confirmation on 409 and resends with confirm', async () => {
    let n = 0;
    const onuploaded = vi.fn();
    const { calls } = mockApi({
      'POST /api/modules/3/booklets': () =>
        n++ === 0 ? json(409, { needs_confirmation: true, estimate_usd: 7.5 }) : json(201, { id: 1 })
    });
    render(UploadBooklet, { moduleId: 3, onuploaded });
    await pick();
    expect(await screen.findByText('Die Erzeugung kostet etwa 7,50 $. Fortfahren?')).toBeInTheDocument();
    expect(calls[0].body).toMatchObject({ confirm: 'false' });
    await userEvent.click(screen.getByRole('button', { name: 'Fortfahren' }));
    await vi.waitFor(() => expect(onuploaded).toHaveBeenCalled());
    expect(calls).toHaveLength(2);
    expect(calls[1].body).toMatchObject({ confirm: 'true' });
    expect(screen.queryByText(/Fortfahren\?/)).not.toBeInTheDocument();
  });

  it.each([
    [422, 'Das PDF enthält keinen Text.'],
    [413, 'Die Datei ist zu gross.']
  ])('shows the message of a %i', async (status, detail) => {
    mockApi({ 'POST /api/modules/3/booklets': () => json(status, { detail }) });
    render(UploadBooklet, { moduleId: 3, onuploaded: vi.fn() });
    await pick();
    expect(await screen.findByText(detail)).toBeInTheDocument();
  });
});
