import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import AdminDashboard from '../pages/admin/AdminDashboard';

vi.mock('../components/dashboard/ThemeToggle', () => ({ default: () => null }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const telemetry = { status: 'ok', overview: { total_models: 1 }, models: {}, credentials: {} };
const ok = data => ({ ok: true, status: 200, json: async () => data });

async function logIn() {
  fireEvent.change(await screen.findByLabelText('Admin Secret'), { target: { value: 'secret' } });
  fireEvent.click(screen.getByRole('button', { name: 'Authenticate' }));
}

describe('admin session recovery', () => {
  it('offers a working retry when telemetry fails after login', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({ status: 401, ok: false })
      .mockResolvedValueOnce(ok({}))
      .mockRejectedValueOnce(new Error('Temporary network failure'))
      .mockResolvedValue(ok(telemetry)));
    render(<AdminDashboard />);
    await logIn();
    expect((await screen.findByRole('alert')).textContent).toContain('Temporary network failure');
    fireEvent.click(screen.getByRole('button', { name: 'Retry telemetry' }));
    expect(await screen.findByText('Worker Agent Usage')).toBeTruthy();
  });

  it('keeps an authenticated session visible when server logout fails', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(ok(telemetry))
      .mockResolvedValueOnce(ok(telemetry))
      .mockResolvedValue({ ok: false, status: 503 }));
    render(<AdminDashboard />);
    await screen.findByText('Worker Agent Usage');
    // Authentication discovery triggers a fresh snapshot before logout.
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole('button', { name: 'Lock' }));
    expect((await screen.findByRole('alert')).textContent).toContain('Could not end the admin session');
    expect(screen.getByText('Worker Agent Usage')).toBeTruthy();
  });
});
