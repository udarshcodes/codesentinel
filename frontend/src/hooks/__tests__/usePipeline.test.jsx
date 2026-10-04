/* global global */
import { describe, it, expect, vi, beforeEach } from 'vitest';
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
    clearCurrentToken: vi.fn()
  }
}));

describe('usePipeline SSE Race Conditions', () => {
  let mockEventSourceInstance;

  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) }) // view
      .mockResolvedValueOnce({ ok: true, json: async () => ({ capability: 'mock-cap' }) }); // stream-capability
    
    mockEventSourceInstance = {
      addEventListener: vi.fn(),
      close: vi.fn()
    };
    
    Object.defineProperty(window, 'EventSource', {
      writable: true,
      value: function() { return mockEventSourceInstance; }
    });
    globalThis.EventSource = window.EventSource;
    credentialStore.getViewToken.mockReturnValue('mock-view-token');
  });

  const getEventListener = (eventName) => {
    const call = mockEventSourceInstance.addEventListener.mock.calls.find(c => c[0] === eventName);
    return call ? call[1] : null;
  };

  it('Exact Stale SSE Race: ignores approval_resolved event if cycle changed', async () => {
    const dispatch = vi.fn();
    let state = {
      status: 'WAITING_FOR_APPROVAL',
      awaiting_approval: true,
      approval_cycle_id: 'cycle-A',
      approval_payload: { fix_id: 'fix-A' }
    };

    const wrapper = ({ children }) => (
      <PipelineContext.Provider value={{ state, dispatch }}>
        {children}
      </PipelineContext.Provider>
    );

    const { rerender } = renderHook(() => usePipeline('task-1'), { wrapper });

    // Wait for hydrate fetch to resolve and SSE to connect
    await act(async () => {
        await new Promise(r => setTimeout(r, 10));
    });

    const onApprovalResolved = getEventListener('approval_resolved');
    expect(onApprovalResolved).toBeTruthy();

    // Switch state to Cycle B
    state = {
      ...state,
      approval_cycle_id: 'cycle-B',
      approval_payload: { fix_id: 'fix-B' }
    };
    rerender();
    
    await act(async () => {
        await Promise.resolve();
    });

    // Simulate an approval_resolved event arriving for Cycle A
    act(() => {
      onApprovalResolved({
        data: JSON.stringify({
          event: 'approval_resolved',
          data: { decision: 'approved', approval_cycle_id: 'cycle-A', fix_id: 'fix-A' }
        })
      });
    });

    // APPROVAL_RESOLVED should NOT be dispatched
    const resolvedCalls = dispatch.mock.calls.filter(c => c[0].type === 'APPROVAL_RESOLVED');
    expect(resolvedCalls.length).toBe(0);
    // credentialStore.clearCurrentToken should NOT be called
    expect(credentialStore.clearCurrentToken).not.toHaveBeenCalled();
  });

  it('Valid SSE Resolution: processes event and clears token if cycle matches', async () => {
    const dispatch = vi.fn();
    let state = {
      status: 'WAITING_FOR_APPROVAL',
      awaiting_approval: true,
      approval_cycle_id: 'cycle-A',
      approval_payload: { fix_id: 'fix-A' }
    };

    const wrapper = ({ children }) => (
      <PipelineContext.Provider value={{ state, dispatch }}>
        {children}
      </PipelineContext.Provider>
    );

    renderHook(() => usePipeline('task-1'), { wrapper });

    // Wait for hydrate
    await act(async () => {
        await new Promise(r => setTimeout(r, 10));
    });

    const onApprovalResolved = getEventListener('approval_resolved');
    expect(onApprovalResolved).toBeTruthy();
    
    act(() => {
      onApprovalResolved({
        data: JSON.stringify({
          event: 'approval_resolved',
          status: 'WAITING_FOR_DISPATCH',
          data: { decision: 'approved', approval_cycle_id: 'cycle-A', fix_id: 'fix-A' }
        })
      });
    });

    // APPROVAL_RESOLVED SHOULD be dispatched
    const resolvedCalls = dispatch.mock.calls.filter(c => c[0].type === 'APPROVAL_RESOLVED');
    expect(resolvedCalls.length).toBe(1);
    expect(resolvedCalls[0][0].payload.decision).toBe('approved');
    expect(resolvedCalls[0][0].payload.status).toBe('WAITING_FOR_DISPATCH');
    expect(resolvedCalls[0][0].payload.approval_cycle_id).toBe('cycle-A');
    expect(credentialStore.clearCurrentToken).toHaveBeenCalledWith('task-1', 'cycle-A');
  });
});
