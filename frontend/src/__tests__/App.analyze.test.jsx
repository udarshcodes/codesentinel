import * as matchers from '@testing-library/jest-dom/matchers';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
expect.extend(matchers);
import App from '../App';
import { credentialStore } from '../services/credentialStore';

vi.mock('../components/dashboard/PipelineDashboard', () => ({
  default: () => <div data-testid="pipeline-dashboard">Dashboard</div>
}));
vi.mock('../pages/admin/AdminDashboard', () => ({
  default: () => <div data-testid="admin-dashboard">Admin Dashboard</div>
}));
vi.mock('../components/landing/LandingPage', () => ({
  default: ({ repoUrlInput, setRepoUrlInput, startAnalysis, isSubmitting, errorMsg }) => (
    <div data-testid="landing-page">
      {errorMsg && <div>{errorMsg}</div>}
      <label htmlFor="repo-input">Repository URL</label>
      <input 
        id="repo-input"
        value={repoUrlInput} 
        onChange={(e) => setRepoUrlInput(e.target.value)} 
      />
      <button onClick={startAnalysis} disabled={isSubmitting}>
        {isSubmitting ? 'Analyzing...' : 'Analyze'}
      </button>
    </div>
  )
}));

describe('App - Analyze Request Error Handling', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation(query => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  afterEach(() => {
    cleanup();
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  const setupAndSubmit = async (url = 'https://github.com/user/repo') => {
    render(<App />);
    const input = screen.getByLabelText(/Repository URL/i);
    fireEvent.change(input, { target: { value: url } });
    
    const analyzeBtn = screen.getByRole('button', { name: /Analyze/i });
    fireEvent.click(analyzeBtn);
  };

  it('7. Frontend handles 429', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: async () => ({ detail: "Rate limit exceeded" })
    });

    await setupAndSubmit();

    await waitFor(() => {
      expect(screen.getByText(/Too many analysis requests/i)).toBeInTheDocument();
    });
    
    expect(screen.getByRole('button', { name: /Analyze/i })).not.toBeDisabled();
  });

  it('8. Frontend handles 500', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ detail: "Internal Server Error" })
    });

    await setupAndSubmit();

    await waitFor(() => {
      expect(screen.getByText(/Internal Server Error|Server returned 500/i)).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /Analyze/i })).not.toBeDisabled();
  });

  it('9. Frontend handles network timeout (AbortError)', async () => {
    const abortError = new Error('AbortError');
    abortError.name = 'AbortError';
    global.fetch = vi.fn().mockRejectedValue(abortError);

    await setupAndSubmit();

    await waitFor(() => {
      expect(screen.getByText(/Connection timed out/i)).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /Analyze/i })).not.toBeDisabled();
  });

  it('10. Frontend never remains permanently in isPipelineRunning state after request failure', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Network failure'));

    await setupAndSubmit();

    await waitFor(() => {
      expect(screen.getByText(/Network failure|Failed to start analysis/i)).toBeInTheDocument();
    });
    expect(screen.queryByTestId('pipeline-dashboard')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Analyze/i })).not.toBeDisabled();
  });

  it('12. New task immediately reaches PipelineDashboard', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        status: "accepted",
        task_id: "test-task-123",
        view_token: "token-123"
      })
    });

    await setupAndSubmit();

    await waitFor(() => {
      expect(screen.getByText(/Analysis Workspace/i)).toBeInTheDocument();
    });
  });
});
