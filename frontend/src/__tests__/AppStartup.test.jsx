import * as matchers from '@testing-library/jest-dom/matchers';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import App from '../App';
expect.extend(matchers);

// Mock matchMedia
window.matchMedia = window.matchMedia || function() {
  return {
    matches: false,
    addListener: function() {},
    removeListener: function() {}
  };
};

// Mock the PipelineDashboard component so we can verify if it's rendered
vi.mock('../components/dashboard/PipelineDashboard', () => ({
  default: ({ taskId }) => <div data-testid="pipeline-dashboard">Dashboard for {taskId}</div>
}));

// Mock the LandingPage to just expose the input and button
vi.mock('../components/landing/LandingPage', () => ({
  default: ({ repoUrlInput, setRepoUrlInput, startAnalysis, isSubmitting, errorMsg }) => (
    <div data-testid="landing-page">
      {errorMsg && <div>{errorMsg}</div>}
      <input 
        data-testid="repo-input"
        value={repoUrlInput} 
        onChange={(e) => setRepoUrlInput(e.target.value)} 
      />
      <button 
        data-testid="start-btn" 
        onClick={startAnalysis}
        disabled={isSubmitting}
      >
        Start
      </button>
    </div>
  )
}));

describe('App Startup State', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('1 & 5. isPipelineRunning true and activeTaskId null shows loading UI, then disappears once activeTaskId exists', async () => {
    // We delay the fetch response to capture the loading state
    let resolveFetch;
    const fetchPromise = new Promise(resolve => {
      resolveFetch = resolve;
    });

    globalThis.fetch.mockReturnValue(fetchPromise);

    render(<App />);

    // Type a repo url
    const input = screen.getByTestId('repo-input');
    fireEvent.change(input, { target: { value: 'https://github.com/foo/bar' } });

    // Click start
    const btn = screen.getByTestId('start-btn');
    fireEvent.click(btn);

    // Now it should show the loading panel
    expect(screen.getByText('Creating analysis task')).toBeInTheDocument();
    expect(screen.getByText('Connecting to analysis worker...')).toBeInTheDocument();
    expect(screen.queryByTestId('pipeline-dashboard')).not.toBeInTheDocument();

    // Resolve the fetch with success
    resolveFetch({
      ok: true,
      json: () => Promise.resolve({ task_id: 'task-123' })
    });

    // Wait for the UI to update
    await waitFor(() => {
      expect(screen.queryByText('Creating analysis task')).not.toBeInTheDocument();
      expect(screen.getByTestId('pipeline-dashboard')).toBeInTheDocument();
      expect(screen.getByText('Dashboard for task-123')).toBeInTheDocument();
    });
  });

  it('2. activeTaskId received shows PipelineDashboard', async () => {
    globalThis.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ task_id: 'task-123' })
    });

    render(<App />);
    fireEvent.change(screen.getByTestId('repo-input'), { target: { value: 'https://github.com/foo/bar' } });
    fireEvent.click(screen.getByTestId('start-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('pipeline-dashboard')).toBeInTheDocument();
    });
  });

  it('3 & 4. API failure shows error state and clears isPipelineRunning', async () => {
    globalThis.fetch.mockResolvedValue({
      ok: false,
      status: 500
    });

    render(<App />);
    fireEvent.change(screen.getByTestId('repo-input'), { target: { value: 'https://github.com/foo/bar' } });
    fireEvent.click(screen.getByTestId('start-btn'));

    await waitFor(() => {
      // Error is displayed
      expect(screen.getByText('Failed to start analysis. Is the backend running?')).toBeInTheDocument();
      // We should be back at the landing page because isPipelineRunning is false
      expect(screen.getByTestId('landing-page')).toBeInTheDocument();
      // The loading panel is gone
      expect(screen.queryByText('Creating analysis task')).not.toBeInTheDocument();
    });
  });

  it('handles timeout correctly', async () => {
    // A fetch that never resolves
    globalThis.fetch.mockImplementation(() => new Promise((resolve, reject) => {
      setTimeout(() => {
        const err = new Error('AbortError');
        err.name = 'AbortError';
        reject(err);
      }, 15000);
    }));

    render(<App />);
    fireEvent.change(screen.getByTestId('repo-input'), { target: { value: 'https://github.com/foo/bar' } });
    fireEvent.click(screen.getByTestId('start-btn'));

    expect(screen.getByText('Creating analysis task')).toBeInTheDocument();

    // Fast forward 15s
    vi.advanceTimersByTime(15000);

    await waitFor(() => {
      expect(screen.getByText('Connection timed out. Could not connect to the backend.')).toBeInTheDocument();
      expect(screen.getByTestId('landing-page')).toBeInTheDocument();
    });
  });
});
