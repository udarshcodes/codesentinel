/* global global */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePipeline } from '../usePipeline';
import { PipelineContext } from '../../context/PipelineContext';

vi.mock('../../services/credentialStore', () => ({
  credentialStore: {
    getViewToken: vi.fn(),
    hasCurrentToken: vi.fn(),
    setCurrentToken: vi.fn(),
    getCurrentToken: vi.fn(),
    clearCurrentToken: vi.fn(),
    clearStaleTokens: vi.fn()
  }
}));

describe('usePipeline Hydration and Error States', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('sets CONNECTION_ERROR when fetchState fails with network error', async () => {
    const dispatch = vi.fn();
    const state = { status: 'QUEUED' };

    global.fetch = vi.fn().mockRejectedValueOnce(new Error('Network Error'));

    const wrapper = ({ children }) => (
      <PipelineContext.Provider value={{ state, dispatch }}>
        {children}
      </PipelineContext.Provider>
    );

    renderHook(() => usePipeline('task-123'), { wrapper });

    await act(async () => {
      await new Promise(r => setTimeout(r, 20));
    });

    const setStatusCalls = dispatch.mock.calls.filter(c => c[0].type === 'SET_STATUS');
    expect(setStatusCalls.length).toBe(1);
    expect(setStatusCalls[0][0].payload.status).toBe('CONNECTION_ERROR');
    expect(setStatusCalls[0][0].payload.pipeline_error).toContain('Network Error');
  });

  it('hydrates COMPLETED state correctly and does not connect SSE', async () => {
    const dispatch = vi.fn();
    const state = { status: 'QUEUED' };

    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        task_id: 'task-123',
        status: 'COMPLETED',
        pipeline_state: { status: 'COMPLETED' }
      })
    });

    const mockEventSource = vi.fn();
    global.EventSource = mockEventSource;

    const wrapper = ({ children }) => (
      <PipelineContext.Provider value={{ state, dispatch }}>
        {children}
      </PipelineContext.Provider>
    );

    renderHook(() => usePipeline('task-123'), { wrapper });

    await act(async () => {
      await new Promise(r => setTimeout(r, 20));
    });

    const hydrateCalls = dispatch.mock.calls.filter(c => c[0].type === 'HYDRATE_STATE');
    expect(hydrateCalls.length).toBe(1);
    expect(hydrateCalls[0][0].payload.status).toBe('COMPLETED');
    expect(mockEventSource).not.toHaveBeenCalled();
  });
});
