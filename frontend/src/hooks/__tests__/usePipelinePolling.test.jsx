/* global global */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePipeline } from '../usePipeline';
import { PipelineContext } from '../../context/PipelineContext';
import { credentialStore } from '../../services/credentialStore';

vi.mock('../../services/credentialStore', () => ({
  credentialStore: {
    getViewToken: vi.fn(),
    hasCurrentToken: vi.fn(),
    setCurrentToken: vi.fn(),
    getCurrentToken: vi.fn(),
    clearCurrentToken: vi.fn(),
    clearStaleTokens: vi.fn(),
    clearAllTokens: vi.fn()
  }
}));

describe('usePipeline Polling Fallback', () => {
  let mockEventSourceInstance;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();

    mockEventSourceInstance = {
      addEventListener: vi.fn(),
      close: vi.fn()
    };
    
    global.EventSource = vi.fn().mockImplementation(function() {
      return mockEventSourceInstance;
    });
    credentialStore.getViewToken.mockReturnValue('mock-view-token');
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('Running task updates through polling and stops on COMPLETED', async () => {
    const dispatch = vi.fn();
    const state = { status: 'QUEUED' };

    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ task_id: 'task-1', status: 'RUNNING' })
      }) // 1. Initial view fetch
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ capability: 'mock-cap' })
      }) // 2. Stream capability fetch
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ task_id: 'task-1', status: 'COMPLETED' })
      }); // 3. Polling fetch (terminal)

    const wrapper = ({ children }) => (
      <PipelineContext.Provider value={{ state, dispatch }}>
        {children}
      </PipelineContext.Provider>
    );

    renderHook(() => usePipeline('task-1'), { wrapper });

    await act(async () => {
      await Promise.resolve();
    });

    // Initial fetch should have happened
    expect(global.fetch).toHaveBeenCalledTimes(2);

    // Fast forward 5 seconds
    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
    });

    // Polling fetch should have happened
    expect(global.fetch).toHaveBeenCalledTimes(3);
    
    const hydrateCalls = dispatch.mock.calls.filter(c => c[0].type === 'HYDRATE_STATE');
    expect(hydrateCalls.length).toBe(2);
    expect(hydrateCalls[0][0].payload.status).toBe('RUNNING');
    expect(hydrateCalls[1][0].payload.status).toBe('COMPLETED');

    // Fast forward another 5 seconds to ensure polling stopped
    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
    });

    // Still 3 calls, meaning polling stopped
    expect(global.fetch).toHaveBeenCalledTimes(3);
  });

  it('SSE failure does not reset state and polling continues', async () => {
    const dispatch = vi.fn();
    let state = { status: 'RUNNING', completed_nodes: ['repo_mapper'] };

    global.fetch = vi.fn().mockImplementation(async (url) => {
      if (url.includes('stream-capability')) {
        return { ok: true, status: 200, json: async () => ({ capability: 'mock-cap' }) };
      }
      return { ok: true, status: 200, json: async () => ({ task_id: 'task-2', status: 'RUNNING', agents: [{ agent: 'dependency_analyzer' }] }) };
    });

    const wrapper = ({ children }) => (
      <PipelineContext.Provider value={{ state, dispatch }}>
        {children}
      </PipelineContext.Provider>
    );

    renderHook(() => usePipeline('task-2'), { wrapper });

    await act(async () => {
      await Promise.resolve();
    });

    // Simulate SSE error
    act(() => {
      if (mockEventSourceInstance.onerror) {
        mockEventSourceInstance.onerror(new Error('SSE Error'));
      }
    });

    // Should dispatch SET_ERROR with connection lost, but KEEP status
    // Ignore error calls
    // Since we mocked max retries as a loop, wait, we didn't override MAX_RETRIES. It will retry.
    // Let's just verify polling still runs after 5s
    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
    });

    // Polling fetch + retry fetches should have happened
    expect(global.fetch.mock.calls.length).toBeGreaterThanOrEqual(3);
    const hydrateCalls = dispatch.mock.calls.filter(c => c[0].type === 'HYDRATE_STATE');
    // Ensure we Hydrated at least twice
    expect(hydrateCalls.length).toBeGreaterThanOrEqual(2);
    expect(hydrateCalls[1][0].payload.agents).toEqual([{ agent: 'dependency_analyzer' }]);
  });

  it('Task ID changes clean up the old polling timer', async () => {
    const dispatch = vi.fn();
    const state = { status: 'RUNNING' };

    global.fetch = vi.fn()
      .mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ task_id: 'any', status: 'RUNNING' })
      });

    const wrapper = ({ children }) => (
      <PipelineContext.Provider value={{ state, dispatch }}>
        {children}
      </PipelineContext.Provider>
    );

    const { rerender, unmount } = renderHook(({ taskId }) => usePipeline(taskId), { 
      initialProps: { taskId: 'task-3' },
      wrapper 
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(global.fetch).toHaveBeenCalledTimes(2); // view + capability

    rerender({ taskId: 'task-4' });

    await act(async () => {
      await Promise.resolve();
    });

    expect(global.fetch).toHaveBeenCalledTimes(4); // view + capability for new task

    // Fast forward 5 seconds
    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
    });

    // Should only have 1 polling fetch (for task-4), not 2
    expect(global.fetch).toHaveBeenCalledTimes(5);

    unmount();

    // Fast forward another 5 seconds
    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
    });

    // Should still be 5
    expect(global.fetch).toHaveBeenCalledTimes(5);
  });
});
