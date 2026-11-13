import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import LandingPage from '../components/landing/LandingPage';
import DiffViewer from '../components/dashboard/DiffViewer';
import PRSummary from '../components/dashboard/PRSummary';
import { credentialStore } from '../services/credentialStore';

vi.mock('../components/landing/Hero', () => ({ default: () => null }));

afterEach(() => { cleanup(); vi.unstubAllGlobals(); sessionStorage.clear(); });

describe('audit regressions', () => {
  it('shows a failed submission in the real landing page', () => {
    render(<LandingPage repoUrlInput="https://github.com/udarshcodes/setu"
      setRepoUrlInput={() => {}} startAnalysis={() => {}} errorMsg="Connection timed out" />);
    expect(screen.getByRole('alert').textContent).toBe('Connection timed out');
  });

  it('can receive patches after an empty first render', () => {
    const { rerender } = render(<DiffViewer state={{ patches: [] }} />);
    rerender(<DiffViewer state={{ patches: [{ file: 'app.py', applied: true }] }} />);
    expect(screen.getByText('app.py')).toBeTruthy();
  });

  it('retries with the task credential and displays hydrated confidence', async () => {
    credentialStore.setViewToken('task-a', 'token-a');
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal('fetch', fetchMock);
    const { rerender } = render(<PRSummary state={null} />);
    rerender(<PRSummary state={{ task_id: 'task-a', status: 'FAILED', pr_error: 'Push failed', confidence: 85 }} />);
    expect(screen.getByText('85.0', { exact: false })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Retry Pull Request Creation' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/job/task-a/retry-pr', {
      method: 'POST', headers: { Authorization: 'Bearer token-a' }
    }));
  });
});
